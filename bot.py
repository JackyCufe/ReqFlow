"""
bot.py — Teams Bot Entry Point (Interactive Pipeline Mode)
Stage 1: Gatekeeping → editable confirmation card (Human-in-the-Loop)
Stage 2: PM editable form → AI generates → confirmation card (2-phase)
Stage 3: RD editable form (no AI pre-fill) → submit
Stage 4: Release review editable form → HARD GATE on scenario_verified
Stage 5-6: AI analysis with Continue/Finish buttons
"""
from __future__ import annotations
import traceback
from typing import Any

from botbuilder.core import (
    ActivityHandler,
    TurnContext,
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
)
from botbuilder.schema import Activity, Attachment
from aiohttp import web

from config.config import TEAMS_APP_ID, TEAMS_APP_PASSWORD, TEAMS_APP_TENANT_ID
from pipeline.pipeline import (
    PipelineState,
    run_stage1_gatekeeper,
    run_stage2_value_transform,
    run_stage3_scenario_test,
    run_stage4_release_review,
    run_stage5_feedback_collect,
    run_stage6_retrospective,
    query_foundry_iq,
    seed_demo_data,
)
from pipeline.cards import (
    gatekeeping_card,
    gatekeeping_edit_card,
    stage2_pm_card,
    stage2_confirm_card,
    stage3a_estimate_card,
    stage3b_result_card,
    stage4_release_card,
    stage5a_survey_card,
    stage5b_feedback_card,
    stage5c_result_card,
    feedback_capture_card,
    rollback_notice_card,
    value_transform_card,
    feedback_analysis_card_interactive,
    process_analysis_card_interactive,
    foundry_iq_alert_card,
    foundry_iq_result_card,
    card_activity,
    teams_compat,
)
from pipeline.foundry_iq import search_similar, write_lesson, archive_to_iq
from pipeline.work_iq import verify_next_person

# ─── Bot Adapter ────────────────────────────────────

_app_id = TEAMS_APP_ID or ""
_app_pw = TEAMS_APP_PASSWORD or ""
SETTINGS = BotFrameworkAdapterSettings(
    app_id=_app_id, app_password=_app_pw,
    channel_auth_tenant=TEAMS_APP_TENANT_ID or None,
)
_adapter = BotFrameworkAdapter(SETTINGS)

# ─── In-Memory Pipeline State (per user) ─────────────

import time

_active_pipelines: dict[str, dict] = {}
"""Structure: {user_id: {"stage": int, "phase": str|None, "state": PipelineState, "last_active": float}}"""

# A pipeline left idle longer than this is considered stale: the next message
# starts a fresh pipeline instead of being treated as a continuation.
_PIPELINE_TTL_SECONDS = 15 * 60  # 15 minutes


# ─── Card Sender Utility ──────────────────────────────

async def _send_card(turn_context: TurnContext, card: dict):
    # Guard against empty/malformed cards rendering as blank attachments
    body_n = len((card or {}).get("body", []))
    if not card or body_n == 0:
        print(f"  [_send_card] ⚠️ EMPTY CARD suppressed: {card}")
        await turn_context.send_activity("⚠️ Internal: empty card suppressed.")
        return
    # Teams cannot render Input.label — downgrade labels to TextBlocks
    card = teams_compat(card)
    activity = Activity(type="message", attachments=[
        Attachment(content_type="application/vnd.microsoft.card.adaptive", content=card)
    ])
    try:
        await turn_context.send_activity(activity)
    except Exception as e:
        import traceback
        print(f"  [_send_card] ❌ send failed: {e}\n{traceback.format_exc()}")
        await turn_context.send_activity(f"⚠️ Card render failed: {str(e)[:200]}")


def _user_id(turn_context: TurnContext) -> str:
    return turn_context.activity.from_property.id or "unknown"


def _user_name(turn_context: TurnContext) -> str:
    return turn_context.activity.from_property.name or "User"


# ─── Stage Dispatchers ────────────────────────────────

async def _show_stage1(turn_context: TurnContext, state: PipelineState):
    """Stage 1: AI gatekeeps → show editable confirmation card (Human-in-the-Loop)."""
    # Only announce "Starting" on the first round; later rounds already showed "Re-analyzing".
    if state.gatekeeping_rounds == 0:
        await turn_context.send_activity("🔄 **Starting Requirement Analysis Pipeline...**")

    similar = search_similar(state.original_text, top=3)
    if similar:
        alert = foundry_iq_alert_card(similar)
        if alert:
            await _send_card(turn_context, alert)

    schema1 = run_stage1_gatekeeper(state)
    verdict = schema1["gatekeeping"]["verdict"]

    if verdict == "rejected":
        await _send_card(turn_context, gatekeeping_card(schema1))
        await turn_context.send_activity(
            "❌ **Pipeline stopped.** Requirement rejected at Stage 1.\n"
            "_Send a new requirement or `?question` to search Foundry IQ._"
        )
        pipeline_data = _active_pipelines.get(_user_id(turn_context))
        if pipeline_data:
            pipeline_data["status"] = "rejected"
    elif verdict == "info_needed":
        pipeline_data = _active_pipelines.get(_user_id(turn_context))
        # Single source of truth: state.gatekeeping_rounds (incremented in run_stage1_gatekeeper)
        rounds = state.gatekeeping_rounds
        if rounds >= 3:
            await _send_card(turn_context, gatekeeping_card(schema1))
            await turn_context.send_activity(
                f"❌ **Max {rounds} rounds reached.** Requirement rejected after insufficient information.\n"
                "_Send a new requirement or `?question` to search Foundry IQ._"
            )
            state.archive("rejection_feedback", stage=1, author=_user_name(turn_context),
                          content={"action": "force_reject", "reason": f"Max {rounds} rounds of info_needed"},
                          tags=["rejection", "stage1", "max_rounds"])
            _active_pipelines.pop(_user_id(turn_context), None)
        else:
            await _send_card(turn_context, gatekeeping_card(schema1))
            await turn_context.send_activity(
                f"❓ **More information needed (round {rounds}/3).** "
                "Provide additional details and I will re-analyze.\n_Type the updated info now._"
            )
            if pipeline_data:
                pipeline_data["status"] = "info_needed"
    else:
        await _send_card(turn_context, gatekeeping_edit_card(schema1))


async def _show_stage2_pm(turn_context: TurnContext, state: PipelineState):
    """Stage 2a: PM editable form — AI pre-fills, PM edits.
    If PM already filled the form (modify/rollback), restore their input instead
    of re-running AI pre-fill (which would overwrite human edits)."""
    gk = state.schemas.get(1, {}).get("gatekeeping", {})

    # Restore prior PM input on modify/rollback — never overwrite human edits
    if getattr(state, "stage2_pm_data", None):
        await turn_context.send_activity("📐 **Stage 2: Product Manager Review** (restoring your previous input)")
        pm = state.stage2_pm_data
        await _send_card(turn_context, stage2_pm_card(
            state.schemas.get(1, {}),
            core_value=pm.get("core_value", ""),
            acceptance_criteria=pm.get("acceptance_criteria", ""),
            feature_def=pm.get("feature_def", ""),
            priority=pm.get("priority", "P1"),
        ))
        return

    await turn_context.send_activity("📐 **Entering Stage 2: Product Manager Review**")
    await turn_context.send_activity("🤖 **AI pre-filling form based on Stage 1 analysis...**")

    # Pre-fill with AI (lightweight single-turn LLM, fast)
    from pipeline.agent_runner import quick_completion, extract_json_from_response

    prompt = (
        "Based on the requirement analysis below, generate draft PM fields as JSON.\n"
        f"Customer: {gk.get('customer_who','customer')}\n"
        f"Scenario: {gk.get('usage_scenario','')}\n"
        f"Problem: {gk.get('problem','')}\n"
        f"Expected: {gk.get('expected_outcome','')}\n\n"
        'Output ONLY valid JSON: {"core_value":"...","acceptance_criteria":"...","feature_def":"...","priority":"P0|P1|P2"}'
    )
    ai_text = quick_completion(prompt, max_tokens=512)
    prefill = extract_json_from_response(ai_text) or {}

    # AI first, fallback to rule-based
    core_value = prefill.get("core_value") or gk.get("expected_outcome") or gk.get("problem", "")[:120]
    acceptance_criteria = prefill.get("acceptance_criteria") or (
        f"1) {gk.get('expected_outcome','Feature delivery')[:150]}\n"
        "2) Integration with existing system verified\n"
        "3) User acceptance testing passed"
    )
    feature_def = prefill.get("feature_def") or (
        f"Feature for {gk.get('customer_who','customer')}: "
        f"{(gk.get('usage_scenario') or gk.get('problem',''))[:150]}"
    )
    priority = prefill.get("priority") or (gk.get("requirement_type") == "customer_reported" and "P0" or "P1")

    await _send_card(turn_context, stage2_pm_card(
        state.schemas.get(1, {}),
        core_value=core_value or "AI pre-fill unavailable — please fill manually",
        acceptance_criteria=acceptance_criteria,
        feature_def=feature_def,
        priority=priority,
    ))


async def _show_stage2_confirm(turn_context: TurnContext, state: PipelineState):
    """Stage 2b: Run AI → show confirmation card with structured criteria + test cases."""
    await turn_context.send_activity("🤖 **AI generating structured criteria + test cases...**")
    schema2 = run_stage2_value_transform(state)
    if schema2:
        await _send_card(turn_context, stage2_confirm_card(schema2))
    else:
        await turn_context.send_activity("⚠️ AI failed to generate test cases. Pipeline stopped.")
        _active_pipelines.pop(_user_id(turn_context), None)


async def _show_stage3_estimate(turn_context: TurnContext, state: PipelineState | None = None):
    """Stage 3a: RD fills technical plan, workload estimate, risks.
    Restores prior estimate on back/rollback so RD input is not lost."""
    await turn_context.send_activity("🧪 **Entering Stage 3a: R&D Estimate**")
    est = getattr(state, "stage3_estimate", None) if state else None
    if est:
        await _send_card(turn_context, stage3a_estimate_card(
            tech_plan=est.get("tech_plan", ""),
            workload_days=est.get("workload_days") or 3,
            risks=est.get("risks", ""),
        ))
    else:
        await _send_card(turn_context, stage3a_estimate_card())


async def _show_stage3_result(turn_context: TurnContext):
    """Stage 3b: RD fills self-test results + approval after development."""
    await turn_context.send_activity("🧪 **Stage 3b: Self-Test Results** — Development complete.")
    await _send_card(turn_context, stage3b_result_card())


async def _show_stage4(turn_context: TurnContext, state: PipelineState):
    """Stage 4: AI pre-judges → show release review editable form with pre-fill."""
    await turn_context.send_activity("🚀 **Entering Stage 4: Release Review**")
    # AI pre-assessment
    schema4 = run_stage4_release_review(state)
    # Pre-fill from pipeline context
    release_value = (state.stage2_pm_data.get("core_value","") if hasattr(state, 'stage2_pm_data')
                     else state.schemas.get(1,{}).get("gatekeeping",{}).get("expected_outcome",""))
    await _send_card(turn_context, stage4_release_card(
        schema4,
        release_value=release_value,
    ))


async def _show_stage5_survey(turn_context: TurnContext, state: PipelineState):
    """Stage 5a: AI-generated survey questions, human edits."""
    await turn_context.send_activity("📊 **Entering Stage 5a: Customer Feedback Survey**")
    await turn_context.send_activity("🤖 **AI generating survey questions based on requirement...**")
    # Generate survey questions from pipeline context
    gk = state.schemas.get(1, {}).get("gatekeeping", {})
    criteria = state.schemas.get(2, {}).get("structured_criteria", [])
    criteria_text = "\n".join(f"- {c.get('description','')}" for c in criteria[:3])
    questions = (
        f"1. Did the new feature solve your [problem]: {gk.get('problem','')}?\n"
        f"2. How satisfied are you? (1-5 scale)\n"
        f"3. Does it meet these criteria:\n{criteria_text}\n"
        f"4. What improvements or issues have you encountered?\n"
        f"5. Any unexpected performance or usability problems?"
    )
    await _send_card(turn_context, stage5a_survey_card(questions=questions, req_id=state.requirement_id))


async def _show_stage5_feedback(turn_context: TurnContext, state: PipelineState):
    """Stage 5b: CSV/text input for customer feedback data."""
    await turn_context.send_activity("📊 **Stage 5b: Feedback Data Input**")
    await _send_card(turn_context, stage5b_feedback_card(req_id=state.requirement_id))


async def _show_stage5_result(turn_context: TurnContext, state: PipelineState):
    """Stage 5: Run AI analysis and show results."""
    await turn_context.send_activity("🤖 **AI analyzing feedback data...**")
    schema5 = run_stage5_feedback_collect(state)
    clusters = schema5.get("complaint_clusters", []) if schema5 else []
    health = schema5.get("customer_health_snapshot", {}) if schema5 else {}
    io_entries = schema5.get("io_potential_entries", []) if schema5 else []

    cluster_text = "\n\n".join(
        f"**{c.get('cluster_id','?')}** ({c.get('severity','?')}): {c.get('description','')}\n"
        f"Sample: {c.get('sample_verbatim','')}"
        for c in clusters[:3]
    ) if clusters else "No complaint clusters identified."

    if isinstance(health, str):
        health_text = health
    else:
        health_text = (
            f"**Health Score**: {health.get('health_score','N/A')}/10\n"
            f"**Trend**: {health.get('trend','N/A')}\n"
            f"**Risk Customers**: {health.get('at_risk_count',0)}"
        ) if health else "No health data available."

    insight_text = "\n".join(
        f"- [{e.get('type','')}] {e.get('summary','')}" for e in io_entries[:3]
    ) if io_entries else "- Feedback data archived for future reference."

    await _send_card(turn_context, stage5c_result_card(
        req_id=state.requirement_id,
        complaint_clusters=cluster_text,
        customer_health=health_text,
        insights=insight_text,
    ))


async def _show_stage6(turn_context: TurnContext, state: PipelineState):
    """Stage 6: Process Analysis (final)."""
    await turn_context.send_activity("🔧 **Running Stage 6: Process Analysis...**")
    schema6 = run_stage6_retrospective(state)
    if schema6:
        await _send_card(turn_context, process_analysis_card_interactive(schema6))
        entries = schema6.get("knowledge_entries_written", [])
        await turn_context.send_activity(
            f"🏁 **Pipeline Complete!**\n\n"
            f"**Requirement**: {state.requirement_title or state.original_text[:80]}\n"
            f"**ID**: {state.requirement_id}\n"
            f"**Knowledge**: {len(entries)} entries written to Foundry IQ\n\n"
            f"_Click Finish to clear._"
        )
    else:
        await turn_context.send_activity("⚠️ Stage 6 failed.")
        _active_pipelines.pop(_user_id(turn_context), None)


# ─── Stage Router ──────────────────────────────────────

_STAGE_HANDLERS = {
    # Stage 1-5 handled inside _handle_card_action with phase tracking
    # Stage 5 phases: survey → feedback → result → continue to 6
    6: _show_stage6,
}


# ─── Bot Class ─────────────────────────────────────────

class RequirementBot(ActivityHandler):
    """AI Requirement Pipeline Bot — interactive, aligned with original design."""

    async def on_message_activity(self, turn_context: TurnContext):
        try:
            await self._dispatch(turn_context)
        except Exception:
            traceback.print_exc()
            await turn_context.send_activity(f"❌ Error: {traceback.format_exc()[:300]}")
            _active_pipelines.pop(_user_id(turn_context), None)

    async def _dispatch(self, turn_context: TurnContext):
        """Route: text → start pipeline  or  card action → handle."""
        uid = _user_id(turn_context)
        activity = turn_context.activity

        if activity.value and isinstance(activity.value, dict):
            action_data = activity.value
            action = action_data.get("action", "")
            # stage may arrive as a string (submit data is stringified for Teams compat)
            try:
                stage = int(action_data.get("stage", 0))
            except (TypeError, ValueError):
                stage = 0
            await self._handle_card_action(turn_context, uid, action, stage)
            return

        text = (activity.text or "").strip()
        if not text:
            await turn_context.send_activity(
                "👋 **AI Requirement Pipeline Agent**\n\n"
                "**Modes:**\n- Type a requirement → Stage-by-stage Pipeline\n"
                "- `?question` → Quick Foundry IQ search\n\nTry sending a requirement now!"
            )
            return

        # ?query → Foundry IQ search (regardless of pipeline state)
        if text.startswith("?"):
            await self._handle_query(turn_context, text[1:].strip())
            return

        if uid in _active_pipelines:
            # Pipeline is active — handle based on status
            pipeline_data = _active_pipelines[uid]

            # TTL: a stale/abandoned pipeline must not hijack a brand-new requirement
            last_active = pipeline_data.get("last_active", 0)
            if time.time() - last_active > _PIPELINE_TTL_SECONDS:
                _active_pipelines.pop(uid, None)
                await turn_context.send_activity(
                    "⏱️ _Previous session expired. Starting fresh._"
                )
                await self._start_pipeline(turn_context, uid, text)
                return
            pipeline_data["last_active"] = time.time()

            status = pipeline_data.get("status", "active")

            if text.lower() == "cancel":
                _active_pipelines.pop(uid, None)
                await turn_context.send_activity("✅ Pipeline cancelled. Send a new requirement to start.")
                return

            if text.startswith("?"):
                await self._handle_query(turn_context, text[1:].strip())
                return

            if text.lower() in ("new", "restart", "reset"):
                _active_pipelines.pop(uid, None)
                await turn_context.send_activity("🆕 **Cleared. Send your new requirement now.**")
                return

            if status == "info_needed":
                state = pipeline_data["state"]
                # Always treat the next message as a supplement when waiting for info.
                # If the user wants to start fresh, they should type 'cancel' first.

                # Genuine supplement — APPEND (not overwrite) and resubmit to Stage 1
                await turn_context.send_activity("🔄 **Re-analyzing with updated information...**")
                # Accumulate multi-round context so earlier info is never lost
                state.accumulated_input = f"{state.accumulated_input}\n{text}".strip()
                pipeline_data["status"] = "active"
                await _show_stage1(turn_context, state)
                return

            if status == "rejected":
                await turn_context.send_activity(
                    "❌ This requirement was rejected. Send a new requirement to start fresh.\n"
                    "_Send `cancel` to clear._"
                )
                return

            if status == "completed":
                # Previous pipeline finished — auto-clear and start fresh
                _active_pipelines.pop(uid, None)
                await self._start_pipeline(turn_context, uid, text)
                return

            # Active pipeline — acknowledge text without blocking
            await turn_context.send_activity(
                "📝 A pipeline is already in progress. Use the card buttons to proceed.\n"
                "_Send `cancel` to stop and start a new requirement._"
            )
            return

        await self._start_pipeline(turn_context, uid, text)

    async def _handle_card_action(
        self, turn_context: TurnContext, uid: str, action: str, stage: int
    ):
        """Handle button clicks from editable cards."""
        if uid not in _active_pipelines:
            await turn_context.send_activity("⚠️ No active pipeline. Send a new requirement.")
            return

        pipeline_data = _active_pipelines[uid]
        pipeline_data["last_active"] = time.time()
        state: PipelineState = pipeline_data["state"]
        current_stage = pipeline_data["stage"]

        # Rollback actions are cross-stage by design — skip stage check for them.
        # Also allow actions from earlier stages (e.g. old card clicked after rollback reset stage).
        _rollback_actions = {"rollback_retry", "rollback_escalate", "rollback_abandon", "feedback_submit"}
        if action not in _rollback_actions and stage != current_stage:
            # Allow if pipeline was rolled back and stage was reset to an earlier value
            if stage != pipeline_data.get("stage"):
                await turn_context.send_activity(
                    f"⚠️ This card is outdated (stage {stage} vs current stage {current_stage}). Please use the latest card."
                )
                return

        form = turn_context.activity.value or {}

        # ── Stage 1 Actions ──────────────────────────
        if action == "confirm_stage1":
            # Human confirmed (possibly edited) 4 fields
            gk = state.schemas[1].get("gatekeeping", {})
            corrections = []
            for key in ("customer_who", "usage_scenario", "problem", "expected_outcome"):
                if form.get(key) and form.get(key) != gk.get(key, ""):
                    corrections.append({"field": key, "old": gk.get(key, ""), "new": form.get(key)})
                    gk[key] = form[key]
            state.schemas[1]["gatekeeping"] = gk
            # Archive human corrections
            if corrections:
                state.archive("human_correction", stage=1, author=_user_name(turn_context),
                              content={"corrections": corrections, "stage": "gatekeeping"},
                              tags=["human_correction"])
            await turn_context.send_activity(
                f"✅ **Stage 1 confirmed.**\n"
                f"📨 Handed off to: **{form.get('next_person', 'PM')}**"
            )
            pipeline_data["stage"] = 2
            pipeline_data["phase"] = "pm"
            await _show_stage2_pm(turn_context, state)

        elif action == "reject_stage1":
            # Capture feedback → write to Foundry IQ (self-improvement loop)
            await _send_card(turn_context, feedback_capture_card(1, "reject", state.requirement_id))

        # ── Stage 2 Actions ──────────────────────────
        elif action == "stage2_generate":
            # PM filled form → store PM data → AI generate
            pm_data = {
                "core_value": form.get("core_value", ""),
                "acceptance_criteria": form.get("acceptance_criteria", ""),
                "feature_def": form.get("feature_def", ""),
                "priority": form.get("priority", "P1"),
            }
            state.stage2_pm_data = pm_data
            # Inject PM data into schema context for AI
            if 1 in state.schemas:
                state.schemas[1]["pm_input"] = pm_data
            pipeline_data["phase"] = "confirm"
            await _show_stage2_confirm(turn_context, state)

        elif action == "stage2_sendback":
            await _send_card(turn_context, feedback_capture_card(2, "send_back", state.requirement_id))

        elif action == "stage2_confirm":
            next_name = form.get('next_person', 'RD')
            wiq = verify_next_person(next_name)
            await turn_context.send_activity(
            f"✅ **Stage 2 confirmed.** 📨 Handed off to: **{next_name}**\n{wiq}")
            pipeline_data["stage"] = 3
            pipeline_data["phase"] = "estimate"
            await _show_stage3_estimate(turn_context, state)

        elif action == "stage2_modify":
            # Go back to PM edit card
            pipeline_data["phase"] = "pm"
            await _show_stage2_pm(turn_context, state)

        # ── Stage 3 Actions ──────────────────────────
        elif action == "stage3a_confirm":
            # RD confirmed estimate → save estimate → show self-test result card
            state.stage3_estimate = {
                "tech_plan": form.get("tech_plan", ""),
                "workload_days": form.get("workload_days", ""),
                "risks": form.get("risks", ""),
            }
            next_name = form.get("next_person", "RD")
            wiq = verify_next_person(next_name)
            await turn_context.send_activity(
                f"✅ **Estimate confirmed.** 📨 Handed off to: **{next_name}**\n{wiq}"
            )
            pipeline_data["phase"] = "result"
            await _show_stage3_result(turn_context)

        elif action == "stage3_back":
            pipeline_data["phase"] = "estimate"
            await _show_stage3_estimate(turn_context, state)

        elif action == "feedback_submit":
            # Write human feedback as rejection_feedback doc (self-improvement loop)
            state.archive("rejection_feedback", stage=stage,
                          author=_user_name(turn_context),
                          content={
                              "action": form.get("original_action", "reject"),
                              "reason": form.get("feedback_reason", ""),
                              "lesson": form.get("feedback_lesson", ""),
                          },
                          tags=["rejection", f"stage{stage}"])
            state.stage_feedback = {
                "stage": stage, "action": form.get("original_action", ""),
                "reason": form.get("feedback_reason", ""),
                "lesson": form.get("feedback_lesson", ""),
            }
            await turn_context.send_activity(
                "✅ **Feedback written to Foundry IQ.** The system just got smarter.\n\n"
                "_Next time a similar requirement arrives, this insight will surface as a Pitfall Alert._"
            )
            # Now trigger rollback — send notice card so user can retry/escalate/abandon
            rollback_to = max(1, stage - 1)
            rework = pipeline_data.get("rework_count", 0) + 1
            pipeline_data["rework_count"] = rework
            state.last_rollback_reason = form.get("feedback_reason", "Not specified")
            await _send_card(turn_context, rollback_notice_card(
                from_stage=stage, to_stage=rollback_to,
                reason=form.get("feedback_reason", ""),
                req_id=state.requirement_id, rework=rework))

        elif action == "feedback_skip":
            await turn_context.send_activity(
                "⏭️ **Feedback skipped.** Pipeline stopped.\n\n"
                "_Send a new requirement or `?question` to search._"
            )
            _active_pipelines.pop(uid, None)

        # ── Stage 3 Actions ──────────────────────────
        elif action == "stage3_submit":
            approval = form.get("approval_result", "approve")
            approval_note = form.get("approval_note", "")

            if approval == "reject":
                rework = pipeline_data.get("rework_count", 0) + 1
                pipeline_data["rework_count"] = rework
                # Carry the rejection reason into state so the rollback target stage can show it
                state.last_rollback_reason = approval_note or "Not specified"
                state.archive("rejection_feedback", stage=3, author=_user_name(turn_context),
                              content={"action": "reject", "reason": approval_note, "rework_count": rework},
                              tags=["rejection", "stage3"])
                await _send_card(turn_context, rollback_notice_card(
                    from_stage=3, to_stage=2, reason=approval_note,
                    req_id=state.requirement_id, rework=rework))
                return

            if approval == "defer":
                await turn_context.send_activity(
                    f"⏸️ **Stage 3 deferred.** Reason: {approval_note or 'Not specified'}"
                )
                return

            if approval == "delegate":
                await turn_context.send_activity(
                    f"↗️ **Stage 3 delegated** to: **{form.get('next_person','unknown')}**"
                )
                return

            # approve
            rd_data = {
                "tech_plan": state.stage3_estimate.get("tech_plan", "") if hasattr(state, 'stage3_estimate') else "",
                "workload_days": state.stage3_estimate.get("workload_days", "") if hasattr(state, 'stage3_estimate') else "",
                "risks": state.stage3_estimate.get("risks", "") if hasattr(state, 'stage3_estimate') else "",
                "scenario_test": form.get("scenario_test", ""),
                "test_note": form.get("test_note", ""),
            }
            state.stage3_rd_data = rd_data
            await turn_context.send_activity("🤖 **AI analyzing test results...**")
            schema3_ai = run_stage3_scenario_test(state) or {}
            state.schemas[3] = {
                "requirement_id": state.requirement_id,
                "test_cases": state.schemas.get(2, {}).get("test_cases", []),
                "rd_tech_plan": rd_data["tech_plan"],
                "rd_workload_days": rd_data["workload_days"],
                "rd_risks": rd_data["risks"],
                "rd_scenario_test": rd_data["scenario_test"],
                "rd_test_note": rd_data["test_note"],
                "ai_test_analysis": schema3_ai.get("test_cases", []),
                "ai_summary": schema3_ai.get("summary", ""),
                "stage": "rd_complete",
            }
            await turn_context.send_activity(
                f"✅ **Stage 3 approved.** 📨 Handed off to: **{form.get('next_person', 'Release Reviewer')}**"
            )
            pipeline_data["stage"] = 4
            pipeline_data["phase"] = None
            await _show_stage4(turn_context, state)

        elif action == "stage3_reject":
            await _send_card(turn_context, feedback_capture_card(3, "reject", state.requirement_id))

        # ── Stage 4 Actions ──────────────────────────
        elif action == "stage4_submit":
            approval = form.get("approval_result", "approve")
            scenario_verified = form.get("scenario_verified", "no")
            approval_note = form.get("approval_note", "")

            # HARD GATE: scenario_verified must be "yes" to proceed
            if approval == "approve" and scenario_verified != "yes":
                await turn_context.send_activity(
                    "🚫 **HARD GATE BLOCKED** 🚫\n\n"
                    "**Customer Scenario Verified** is **No**.\n"
                    "Release **cannot proceed** until all customer scenarios pass.\n\n"
                    "_Re-fill the form after scenarios are verified._"
                )
                await _show_stage4(turn_context, state)
                return

            if approval == "reject":
                state.archive("rejection_feedback", stage=4, author=_user_name(turn_context),
                              content={"action": "reject", "reason": approval_note},
                              tags=["rejection", "stage4"])
                await turn_context.send_activity(
                    f"❌ **Stage 4 rejected.** Pipeline stopped.\n"
                    f"_Reason: {approval_note or 'Not specified'}_"
                )
                _active_pipelines.pop(uid, None)
                return

            if approval == "defer":
                state.archive("rejection_feedback", stage=4, author=_user_name(turn_context),
                              content={"action": "defer", "reason": approval_note},
                              tags=["deferred", "stage4"])
                await turn_context.send_activity(
                    f"⏸️ **Stage 4 deferred.** Pipeline paused.\n"
                    f"_Reason: {approval_note or 'Not specified'}_"
                )
                return

            if approval == "delegate":
                await turn_context.send_activity(
                    f"↗️ **Stage 4 delegated** to: **{form.get('next_person','unknown')}**"
                )
                # Re-show card for new person
                return

            # approve + hard gate passed
            release_data = {
                "release_value": form.get("release_value", ""),
                "version": form.get("version", ""),
                "release_date": form.get("release_date", ""),
                "scenario_verified": scenario_verified,
                "release_risk": form.get("release_risk", ""),
                "rollback_plan": form.get("rollback_plan", ""),
                "approval_result": approval,
                "approval_note": approval_note,
            }
            state.stage4_release_data = release_data
            next_name = form.get('next_person', 'After-sales')
            wiq = verify_next_person(next_name)
            await turn_context.send_activity(
            f"✅ **Stage 4 approved — Hard gate passed.** 📨 Handed off to: **{next_name}**\n{wiq}")
            pipeline_data["stage"] = 5
            pipeline_data["phase"] = "survey"
            await _show_stage5_survey(turn_context, state)

        # ── Stage 5 Actions ──────────────────────────
        elif action == "stage5a_submit":
            state.stage5_survey = {"questions": form.get("survey_questions", "")}
            state.archive("survey_design", stage=5, author=_user_name(turn_context),
                          content={"survey_questions": form.get("survey_questions", "")},
                          tags=["survey_design"])
            next_name = form.get('next_person', 'Feedback team')
            wiq = verify_next_person(next_name)
            await turn_context.send_activity(
            f"✅ **Survey published.** 📨 Handed off to: **{next_name}**\n{wiq}")
            pipeline_data["phase"] = "feedback"
            await _show_stage5_feedback(turn_context, state)

        elif action == "stage5b_analyze":
            feedback_data = form.get("feedback_data", "")
            # Inject feedback data into state for AI analysis
            state.stage5_raw_feedback = feedback_data
            await _show_stage5_result(turn_context, state)
            pipeline_data["phase"] = "result"

        elif action == "stage5_continue":
            await turn_context.send_activity("✅ **Stage 5 complete.** Proceeding to Stage 6 Process Analysis.")
            pipeline_data["stage"] = 6
            pipeline_data["phase"] = None
            await _show_stage6(turn_context, state)

        # ── Rollback Actions ─────────────────────────
        elif action == "rollback_retry":
            try:
                target_stage = int(form.get("stage", 2))
            except (TypeError, ValueError):
                target_stage = 2
            pipeline_data["stage"] = target_stage
            pipeline_data["status"] = "active"
            await turn_context.send_activity(
                f"🔄 **Resubmitting from Stage {target_stage}...**"
            )
            # Surface the rejection reason so the PM addresses it this round (in-pipeline feedback loop)
            reason = getattr(state, "last_rollback_reason", None)
            if reason:
                await turn_context.send_activity(
                    f"📌 **Why it was sent back:** {reason}\n_Adjust the form below to address this._"
                )
            if target_stage == 2:
                pipeline_data["phase"] = "pm"
                await _show_stage2_pm(turn_context, state)
            elif target_stage == 1:
                pipeline_data["phase"] = None
                await _show_stage1(turn_context, state)

        elif action == "rollback_escalate":
            try:
                from_stage = int(form.get("from_stage", 3))
            except (TypeError, ValueError):
                from_stage = 3
            if from_stage == 3:
                await _send_card(turn_context, rollback_notice_card(
                    from_stage=3, to_stage=1, reason="Escalated further up",
                    req_id=state.requirement_id,
                    rework=pipeline_data.get("rework_count", 1)))
            else:
                await turn_context.send_activity("⬆️ **Escalated to top.** Pipeline stopped.")
                _active_pipelines.pop(uid, None)

        elif action == "rollback_abandon":
            await turn_context.send_activity("🏳️ **Requirement abandoned.** Pipeline stopped.")
            _active_pipelines.pop(uid, None)

        # ── Stage 6 Actions ──
        elif action == "next":
            next_stage = stage + 1
            handler = _STAGE_HANDLERS.get(next_stage)
            if handler:
                pipeline_data["stage"] = next_stage
                await handler(turn_context, state)
            else:
                await turn_context.send_activity("⚠️ Unknown next stage. Pipeline stopped.")
                _active_pipelines.pop(uid, None)

        elif action == "stop":
            await turn_context.send_activity("🛑 **Pipeline stopped at user request.**")
            _active_pipelines.pop(uid, None)

        elif action == "finish":
            await turn_context.send_activity(
                "🏁 **Pipeline complete!**\n\n"
                f"**Requirement**: {state.requirement_title or state.original_text[:80]}\n"
                f"**ID**: {state.requirement_id}\n\n_Send another requirement or `?question`._"
            )
            _active_pipelines.pop(uid, None)

        else:
            await turn_context.send_activity(f"⚠️ Unknown action: `{action}`.")
            _active_pipelines.pop(uid, None)

    async def _start_pipeline(self, turn_context: TurnContext, uid: str, text: str):
        """Initialize pipeline and show Stage 1."""
        seed_demo_data()
        name = _user_name(turn_context)
        state = PipelineState(text, submitted_by=name)
        _active_pipelines[uid] = {"stage": 1, "phase": None, "state": state,
                                  "last_active": time.time()}
        await _show_stage1(turn_context, state)

    async def _handle_query(self, turn_context: TurnContext, question: str):
        """Quick Foundry IQ knowledge search."""
        if not question:
            await turn_context.send_activity("Please provide a question after `?`")
            return
        await turn_context.send_activity(f"🔍 Searching Foundry IQ for: {question}...")
        try:
            results = search_similar(question, top=3)
            card = foundry_iq_result_card(question, results)
            await _send_card(turn_context, card)
        except Exception as e:
            await turn_context.send_activity(f"Search error: {str(e)}")

    async def on_members_added_activity(self, members_added, turn_context):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    "👋 Hello! I am the **AI Requirement Pipeline Agent**.\n\n"
                    "**Two modes:**\n- Type a requirement → Stage-by-stage Pipeline\n"
                    "- `?question` → Quick Foundry IQ search\n\n"
                    "**Stages**: Gatekeeping → PM Review → R&D Review → Release Review → Feedback → Process Analysis\n"
                    "Each stage uses **editable forms** — you decide the content.\n\n"
                    "Try sending a requirement now!"
                )


# ─── HTTP Server ────────────────────────────────────

_bot = RequirementBot()


async def messages_handler(request: web.Request) -> web.Response:
    if "application/json" in request.headers.get("Content-Type", ""):
        body = await request.json()
    else:
        return web.Response(status=415)

    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    try:
        response = await _adapter.process_activity(activity, auth_header, _bot.on_turn)
        if response:
            return web.json_response(data=response.body, status=response.status)
        return web.Response(status=200)
    except Exception:
        traceback.print_exc()
        return web.Response(status=500)


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/api/messages", messages_handler)
    return app


if __name__ == "__main__":
    print("=" * 55)
    print("  AI Requirement Pipeline — Interactive Bot Server")
    print("  Endpoint: http://localhost:3978/api/messages")
    print("=" * 55)
    app = create_app()
    web.run_app(app, port=3978)
