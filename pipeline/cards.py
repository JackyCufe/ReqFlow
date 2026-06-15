"""
cards.py — Adaptive Card templates for 6-Agent Pipeline stages.
Rendered natively in Bot Framework Emulator and Microsoft Teams.
"""
from __future__ import annotations
from typing import Any


def teams_compat(card: dict) -> dict:
    """Make an Adaptive Card render reliably in Microsoft Teams / Web Chat.

    Fixes host-renderer pitfalls that cause the WHOLE card to render blank:
    1. `Input.*` elements using the `label` property (AC 1.3+) — converted to
       a preceding TextBlock and the `label` is stripped.
    2. `Action.Submit` `data` values that are non-strings (e.g. integers like
       `stage: 1`) — coerced to strings, since some hosts reject the card
       outright when submit data is not string-typed.
    3. `Input.*` with `isRequired: true` — CONFIRMED via binary search to make
       Teams render the entire card blank (even when `errorMessage` is present).
       We strip `isRequired`/`errorMessage`; required-field validation is
       enforced server-side in the bot handlers instead.
    """
    if not isinstance(card, dict):
        return card

    # ── Fix 1 + 3: Input labels and required-flag removal ──
    body = card.get("body")
    if isinstance(body, list):
        new_body: list[dict] = []
        for item in body:
            if isinstance(item, dict) and str(item.get("type", "")).startswith("Input."):
                if item.get("label"):
                    label_text = item.pop("label")
                    new_body.append({
                        "type": "TextBlock",
                        "text": f"**{label_text}**",
                        "wrap": True,
                        "spacing": "Small",
                    })
                # isRequired blanks the whole card in Teams — remove it
                item.pop("isRequired", None)
                item.pop("errorMessage", None)
            new_body.append(item)
        card["body"] = new_body

    # ── Fix 2: stringify Action.Submit data values ──
    def _stringify_data(actions):
        for a in actions or []:
            data = a.get("data")
            if isinstance(data, dict):
                a["data"] = {k: (v if isinstance(v, str) else str(v)) for k, v in data.items()}
    _stringify_data(card.get("actions"))

    return card


def _factset(facts: dict) -> dict:
    """Build a FactSet from a dict of key-value pairs."""
    return {
        "type": "FactSet",
        "facts": [{"title": k, "value": str(v)} for k, v in facts.items()],
        "spacing": "Medium",
    }


def _basic_card(title: str, sections: list[dict | str | list], footer: str = "") -> dict:
    """Build a basic Adaptive Card with sections."""
    body = [
        {
            "type": "TextBlock",
            "text": title,
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        },
    ]
    for section in sections:
        if isinstance(section, str):
            body.append({
                "type": "TextBlock", "text": section, "wrap": True, "spacing": "Medium",
            })
        elif isinstance(section, dict):
            # Key-value pairs → FactSet for proper table-like rendering
            body.append(_factset(section))
        elif isinstance(section, list):
            body.append({
                "type": "TextBlock",
                "text": "\n".join(f"- {item}" for item in section),
                "wrap": True, "spacing": "Medium",
            })
    if footer:
        body.append({
            "type": "TextBlock", "text": footer, "wrap": True,
            "spacing": "Large", "size": "Small", "color": "Accent",
        })
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": body,
    }


def gatekeeping_card(schema1: dict) -> dict:
    gk = schema1.get("gatekeeping", {})
    v = gk.get("verdict", "?")
    emoji = {"approved": "✅ Passed", "rejected": "❌ Rejected", "info_needed": "❓ More Info"}.get(v, "")
    sections: list[Any] = [
        f"**Verdict**: {emoji}",
        {
            "Type": gk.get("requirement_type", ""),
            "Source Traceable": "Yes" if gk.get("source_traceable") else "No",
            "Customer": gk.get("customer_who") or "N/A",
            "Scenario": gk.get("usage_scenario") or "N/A",
            "Problem": gk.get("problem") or "N/A",
            "Expected Outcome": gk.get("expected_outcome") or "N/A",
        },
    ]
    if v == "rejected":
        sections.append(f"**Reason**: {gk.get('reject_reason', '')}")
    elif v == "info_needed":
        qs = gk.get("followup_questions", [])
        if qs:
            sections.append([f"Q{i+1}. {q}" for i, q in enumerate(qs)])
    return _basic_card(
        "🛡️ Stage 1: Gatekeeping",
        sections,
        f"Requirement ID: {schema1.get('requirement_id', '')}",
    )


def value_transform_card(schema2: dict) -> dict:
    criteria = schema2.get("structured_criteria", [])
    sections: list[Any] = [
        {
            "Priority": schema2.get("pm_priority", "N/A"),
            "Core Value": schema2.get("pm_core_value", "N/A"),
            "Feature": schema2.get("pm_feature_def", "N/A"),
        },
    ]
    if criteria:
        items = [
            f"**{c.get('criterion_id', '')}**: {c.get('description', '')} → *{c.get('threshold', '')}*"
            for c in criteria
        ]
        sections.append(items)
    sections.append(f"{len(schema2.get('test_cases', []))} test cases generated")
    return _basic_card(
        "📐 Stage 2: Value Transform — [→ PM Review]",
        sections,
        "_Demo: auto-approved for pipeline continuation_",
    )


def scenario_test_card(schema3: dict) -> dict:
    tc_list = schema3.get("test_cases", [])
    items = [
        f"**{tc.get('case_id', '')}** | {tc.get('actor', '')}: {tc.get('expected_result', '')[:80]}"
        for tc in tc_list[:5]
    ]
    return _basic_card(
        "🧪 Stage 3: Scenario Test Cases [→ Tester]",
        [items] if items else [f"{len(tc_list)} total test cases"],
        f"Tester: {schema3.get('tester_confirmed_by', 'QA Team')}",
    )


def release_review_card(schema4: dict) -> dict:
    verdict = schema4.get("release_verdict", "?")
    emoji = "✅ Approved" if verdict == "approved" else "🚫 Blocked"
    reqs = schema4.get("requirements", [])
    items = [
        f"{'✅' if r.get('acceptance_verdict') == 'pass' else '❌'} **{r.get('requirement_id', '')}** [{r.get('importance', '')}]"
        for r in reqs
    ]
    sections: list[Any] = [f"**Decision**: {emoji}"]
    if items:
        sections.append(items)
    if verdict == "approved" and schema4.get("core_value_statement"):
        sections.append(f"_Delivers: {schema4['core_value_statement']}_")
    return _basic_card("🚀 Stage 4: Release Review", sections, "Confirmed by: PM")


def feedback_analysis_card(schema5: dict) -> dict:
    clusters = schema5.get("complaint_clusters", [])
    positives = schema5.get("unexpected_positives", [])
    sections: list[Any] = []
    if clusters:
        items = [
            f"🔴 **{c.get('theme', '')}** [{c.get('severity', '')}] ({c.get('frequency', '')})\n"
            f"\"{c.get('verbatim_sample', '')[:120]}\""
            for c in clusters
        ]
        sections.append(items)
    if positives:
        sections.append([f"🟢 {p.get('description', '')}" for p in positives])
    if schema5.get("customer_health_snapshot"):
        sections.append(schema5["customer_health_snapshot"][:200])
    return _basic_card(
        "👥 Stage 5: Customer Feedback Analysis",
        sections,
        f"{len(clusters)} complaint clusters from customer data",
    )


def process_analysis_card(schema6: dict) -> dict:
    roi = schema6.get("roi_verdict", {})
    bottlenecks = schema6.get("bottlenecks", [])
    knowledge = schema6.get("knowledge_entries_written", [])
    sections: list[Any] = [f"**ROI**: {roi.get('summary', 'N/A')}"]
    if bottlenecks:
        items = [
                        f"⏱️ **{b.get('stage', '')}**: {b.get('description', '')} ({float(b.get('duration_hours', 0) or 0):.0f}h)"
            for b in bottlenecks[:3]
        ]
        sections.append(items)
    if knowledge:
        sections.append(f"📝 {len(knowledge)} knowledge entries → **Foundry IQ**")
    if schema6.get("summary_for_team"):
        sections.append(schema6["summary_for_team"][:300])
    return _basic_card(
        "🔧 Stage 6: Process Analysis — Team Collaboration",
        sections,
        "All insights saved to Foundry IQ",
    )


def foundry_iq_alert_card(similar_reqs: list[dict]) -> dict | None:
    """Pre-pipeline alert: similar historical requirements with pitfalls."""
    if not similar_reqs:
        return None

    sections: list[Any] = [
        f"⚠️ **{len(similar_reqs)} similar requirements found in organizational memory**",
    ]

    for i, r in enumerate(similar_reqs[:3]):
        content = r.get("content") or r
        pitfalls = content.get("pitfalls", []) if isinstance(content, dict) else []
        pitfall_text = "\n".join(f"  • {p}" for p in pitfalls[:2]) if pitfalls else "  • None recorded"
        req_title = r.get("requirement_title") or content.get("requirement", "") if isinstance(content, dict) else ""

        sections.append(
            f"**[{i+1}] {r.get('id', '')}**: {str(req_title)[:100]}\n"
            f"Status: {str(content.get('resolution', 'Unknown'))[:80]}\n"
            f"Pitfalls:\n{pitfall_text}"
        )

    sections.append("*Pipeline will continue — this alert is informational.*")

    return _basic_card(
        "⚠️ Foundry IQ Alert — Historical Pitfalls Detected",
        sections,
        "Learn from history. Don't repeat mistakes.",
    )


def foundry_iq_result_card(question: str, results: list[dict]) -> dict:
    """Foundry IQ search result card — clean layout, one result per block."""
    if not results:
        return _basic_card(
            "🔍 Foundry IQ Search",
            [f"_No records found for: {question}_\n\nSubmit as a new requirement to start the pipeline."],
        )

    body: list[dict] = [
        {"type": "TextBlock", "text": f"🔍 Foundry IQ: {question[:60]}",
         "weight": "Bolder", "size": "Large", "wrap": True},
        {"type": "TextBlock",
         "text": f"**{len(results)} record{'s' if len(results) != 1 else ''} from organizational memory**",
         "wrap": True, "spacing": "Small", "color": "Accent", "size": "Small"},
    ]

    for i, r in enumerate(results[:3]):
        content = r.get("content") or {}
        pitfalls = content.get("pitfalls", []) if isinstance(content, dict) else []
        req_title = r.get("requirement_title") or (
            content.get("requirement", "") if isinstance(content, dict) else "")
        resolution = (content.get("resolution", "") if isinstance(content, dict) else "") or ""

        # Separator between results
        body.append({"type": "TextBlock", "text": "---", "spacing": "Medium"})

        # Result header
        body.append({
            "type": "TextBlock",
            "text": f"**[{i+1}]** {str(req_title)[:80]}",
            "wrap": True, "weight": "Bolder", "spacing": "Small",
        })

        # Resolution
        if resolution:
            body.append({
                "type": "TextBlock",
                "text": f"✅ **Resolution:** {str(resolution)[:120]}{'...' if len(resolution) > 120 else ''}",
                "wrap": True, "spacing": "Small", "size": "Small",
            })

        # Pitfalls — each on its own line
        if pitfalls:
            body.append({
                "type": "TextBlock",
                "text": "⚠️ **Pitfalls:**",
                "wrap": True, "spacing": "Small", "weight": "Bolder", "size": "Small",
            })
            for p in pitfalls[:3]:
                body.append({
                    "type": "TextBlock",
                    "text": f"• {str(p)[:120]}{'...' if len(str(p)) > 120 else ''}",
                    "wrap": True, "spacing": "None", "size": "Small",
                })
        else:
            body.append({
                "type": "TextBlock",
                "text": "⚠️ **Pitfalls:** None recorded",
                "wrap": True, "spacing": "Small", "size": "Small", "isSubtle": True,
            })

    body.append({
        "type": "TextBlock",
        "text": "_Learn from history. Don't repeat mistakes._",
        "wrap": True, "spacing": "Medium", "isSubtle": True, "size": "Small",
    })

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.3",
        "body": body,
    }



def card_activity(card: dict) -> dict:
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card,
        }],
    }


# ─── Interactive Card Builders (with Action.Submit buttons) ──────

def _add_actions(card: dict, actions: list[dict]) -> dict:
    """Attach interactive Action.Submit buttons to a card."""
    card["actions"] = actions
    return card


def gatekeeping_card_interactive(schema1: dict) -> dict:
    """Stage 1 card with Approve / Reject / Need More Info buttons."""
    return _add_actions(gatekeeping_card(schema1), [
        {"type": "Action.Submit", "title": "✅ Approve", "data": {
            "action": "approve", "stage": 1,
            "req_id": schema1.get("requirement_id", ""),
        }},
        {"type": "Action.Submit", "title": "❌ Reject", "data": {
            "action": "reject", "stage": 1,
            "req_id": schema1.get("requirement_id", ""),
        }},
        {"type": "Action.Submit", "title": "❓ Need More Info", "data": {
            "action": "info_needed", "stage": 1,
            "req_id": schema1.get("requirement_id", ""),
        }},
    ])


# ─── Stage 1 Editable Confirmation Card ─────────────────

def gatekeeping_edit_card(schema1: dict) -> dict:
    """Stage 1 confirmation card with EDITABLE 4-field form.
    AI pre-fills extracted values; human can correct before confirming.
    Matches the original Human-in-the-Loop design where sales/PM
    review and potentially edit the AI's extraction.
    """
    gk = schema1.get("gatekeeping", {})
    req_id = schema1.get("requirement_id", "")
    verdict = gk.get("verdict", "")

    emoji = {"approved": "✅ Passed", "rejected": "❌ Rejected", "info_needed": "❓ More Info"}.get(verdict, "")

    body = [
        {"type": "TextBlock", "text": "🛡️ Stage 1: Gatekeeping — Confirm & Edit",
         "weight": "Bolder", "size": "Large", "wrap": True},
        {"type": "TextBlock", "text": f"**Verdict**: {emoji}  |  **Type**: {gk.get('requirement_type','')}  |  **ID**: {req_id}",
         "wrap": True, "spacing": "Medium", "size": "Small", "color": "Accent"},
        {"type": "TextBlock", "text": "⚠️ **AI extracted the fields below. You can edit any field before confirming.**",
         "wrap": True, "spacing": "Medium", "weight": "Bolder"},
        # Editable fields
        {"type": "Input.Text", "id": "customer_who", "label": "👤 Customer (who)",
         "value": gk.get("customer_who") or "", "isMultiline": False},
        {"type": "Input.Text", "id": "usage_scenario", "label": "📋 Usage Scenario",
         "value": gk.get("usage_scenario") or "", "isMultiline": True},
        {"type": "Input.Text", "id": "problem", "label": "⚠️ Problem / Pain Point",
         "value": gk.get("problem") or "", "isMultiline": True},
        {"type": "Input.Text", "id": "expected_outcome", "label": "🎯 Expected Outcome",
         "value": gk.get("expected_outcome") or "", "isMultiline": True},
        {"type": "Input.Text", "id": "next_person", "label": "👤 Next Owner (PM)",
         "placeholder": "e.g. Zhang San", "value": "Jacky", "isRequired": True},
    ]

    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": body,
        "actions": [
            {"type": "Action.Submit", "title": "✅ Confirm & Continue to Stage 2", "data": {
                "action": "confirm_stage1", "stage": 1,
                "req_id": req_id,
            }},
            {"type": "Action.Submit", "title": "❌ Reject & Stop", "data": {
                "action": "reject_stage1", "stage": 1,
                "req_id": req_id,
            }},
        ],
    }
    return card


def value_transform_card_interactive(schema2: dict) -> dict:
    """Stage 2 card with Continue button."""
    return _add_actions(value_transform_card(schema2), [
        {"type": "Action.Submit", "title": "▶️ Continue to Scenario Test", "data": {
            "action": "next", "stage": 2,
        }},
    ])


# ─── Stage 2: PM Editable Form (Phase 2a) ────────────────

def stage2_pm_card(
    schema1: dict,
    core_value: str = "",
    acceptance_criteria: str = "",
    feature_def: str = "",
    priority: str = "P1",
) -> dict:
    """Stage 2a: PM editable form — fill acceptance criteria, feature def, priority.
    AI pre-fills values; PM edits then clicks 'Generate Test Cases'."""
    gk = schema1.get("gatekeeping", {})
    req_id = schema1.get("requirement_id", "")

    body = [
        {"type": "TextBlock", "text": "📐 Stage 2: Product Manager Review",
         "weight": "Bolder", "size": "Large", "wrap": True},
        {"type": "TextBlock", "text": f"**Requirement**: {req_id}  |  **Type**: {gk.get('requirement_type','')}",
         "wrap": True, "spacing": "Small", "size": "Small", "color": "Accent"},
        {"type": "TextBlock", "text": "**AI has pre-filled suggestions below. Review and edit. ⚠️ All fields required.**",
         "wrap": True, "spacing": "Medium", "weight": "Bolder"},
        {"type": "Input.Text", "id": "core_value", "label": "💡 Core Value (what problem does this solve?)",
         "value": core_value or (gk.get("expected_outcome") or ""),
         "placeholder": "e.g. Reduce QC operator manual classification time by 90%",
         "isMultiline": True, "isRequired": True},
        {"type": "Input.Text", "id": "acceptance_criteria", "label": "📏 Acceptance Criteria (quantified)",
         "value": acceptance_criteria or "",
         "placeholder": "e.g. 1) Photo classification ≤2s  2) Recall ≥95% on 3 defect types  3) Integration with MES",
         "isMultiline": True, "isRequired": True},
        {"type": "Input.Text", "id": "feature_def", "label": "🏗️ Feature Definition (product scope)",
         "value": feature_def or "",
         "placeholder": "e.g. AI vision module on edge device, outputs classification label to MES",
         "isMultiline": True, "isRequired": True},
        {"type": "Input.ChoiceSet", "id": "priority", "label": "⚡ Priority",
         "style": "expanded", "isRequired": True,
         "value": priority or "P1",
         "choices": [
             {"title": "SP — Strategic Priority", "value": "SP"},
             {"title": "P0 — Critical", "value": "P0"},
             {"title": "P1 — High", "value": "P1"},
             {"title": "P2 — Normal", "value": "P2"},
         ]},
    ]
    return {
        "type": "AdaptiveCard", "version": "1.5",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "body": body,
        "actions": [
            {"type": "Action.Submit", "title": "🔍 Generate Test Cases", "data": {
                "action": "stage2_generate", "stage": 2,
                "req_id": req_id,
            }},
            {"type": "Action.Submit", "title": "↩️ Send Back to Sales", "data": {
                "action": "stage2_sendback", "stage": 2,
                "req_id": req_id,
            }},
        ],
    }


# ─── Stage 2b: PM Confirmation Card (after AI generates) ──

def stage2_confirm_card(schema2: dict) -> dict:
    """Stage 2b: PM confirmation — editable criteria + editable test cases.
    PM can correct AI-generated acceptance criteria and test cases before confirming."""
    criteria = schema2.get("structured_criteria", [])
    test_cases = schema2.get("test_cases", [])
    req_id = schema2.get("requirement_id", "")

    body = [
        {"type": "TextBlock", "text": "📐 Stage 2: Confirm & Edit",
         "weight": "Bolder", "size": "Large", "wrap": True},
        {"type": "TextBlock", "text": f"**Priority**: {schema2.get('pm_priority','—')}  |  **ID**: {req_id}",
         "wrap": True, "spacing": "Small", "size": "Small", "color": "Accent"},
        {"type": "TextBlock", "text": "⚠️ **AI generated the content below. Edit any field before confirming.**",
         "wrap": True, "spacing": "Medium", "weight": "Bolder"},
    ]

    # Editable: structured criteria
    criteria_text = "\n\n".join(
        f"**{c.get('criterion_id','?')}**\n"
        f"Description: {c.get('description','')}\n"
        f"Threshold: {c.get('threshold','—')}\n"
        f"Method: {c.get('measurement_method','—')}"
        for c in criteria
    )
    body.append({"type": "Input.Text", "id": "criteria_edited",
                 "label": "📋 Acceptance Criteria (edit if needed)",
                 "value": criteria_text,
                 "isMultiline": True})

    # Editable: test cases
    tc_text = "\n\n---\n\n".join(
        f"**{tc.get('case_id','?')}** | Actor: {tc.get('actor','?')}\n"
        f"Precondition: {tc.get('precondition','')}\n"
        f"Steps: {tc.get('steps','')}\n"
        f"Expected: {tc.get('expected_result','')}"
        for tc in test_cases
    )
    body.append({"type": "Input.Text", "id": "test_cases_edited",
                 "label": "✏️ Test Cases (edit if needed)",
                 "value": tc_text,
                 "isMultiline": True})
    body.append({"type": "Input.Text", "id": "next_person", "label": "👤 Next Owner (RD)",
                 "placeholder": "e.g. Li Si", "value": "Jacky", "isRequired": True})

    return {
        "type": "AdaptiveCard", "version": "1.5",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "body": body,
        "actions": [
            {"type": "Action.Submit", "title": "✅ Confirm → Stage 3 (RD Review)", "data": {
                "action": "stage2_confirm", "stage": 2,
            }},
            {"type": "Action.Submit", "title": "↩️ Modify", "data": {
                "action": "stage2_modify", "stage": 2,
            }},
        ],
    }


# ─── Stage 3a: RD Estimate Form ─────────────────────────

def stage3a_estimate_card(tech_plan: str = "", workload_days: float = 3, risks: str = "") -> dict:
    """Stage 3a: RD fills technical plan, workload estimate, risks.
    First phase — RD estimates before actual development."""
    body = [
        {"type": "TextBlock", "text": "🧪 Stage 3a: R&D Estimate",
         "weight": "Bolder", "size": "Large", "wrap": True},
        {"type": "TextBlock", "text": "**First: describe the technical approach and estimated effort.**",
         "wrap": True, "spacing": "Small", "size": "Small", "color": "Accent"},
        {"type": "Input.Text", "id": "tech_plan", "label": "🔧 Technical Plan",
         "value": tech_plan,
         "placeholder": "e.g. Azure Custom Vision + Edge container on IPC-3000, REST API to MES",
         "isMultiline": True, "isRequired": True},
        {"type": "Input.Number", "id": "workload_days", "label": "📅 Estimated Workload (person-days)",
         "min": 0.5, "max": 90, "value": workload_days, "isRequired": True},
        {"type": "Input.Text", "id": "risks", "label": "⚠️ Technical Risks",
         "value": risks,
         "placeholder": "e.g. Factory lighting variance may degrade model accuracy; need on-site calibration",
         "isMultiline": True, "isRequired": True},
        {"type": "Input.Text", "id": "next_person", "label": "👤 Next Owner (Self-test)",
         "placeholder": "e.g. Same person", "value": "Jacky", "isRequired": True},
    ]
    return {
        "type": "AdaptiveCard", "version": "1.5",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "body": body,
        "actions": [
            {"type": "Action.Submit", "title": "🔧 Confirm Estimate → Start Testing", "data": {
                "action": "stage3a_confirm", "stage": 3,
            }},
            {"type": "Action.Submit", "title": "↩️ Send Back to PM", "data": {
                "action": "stage3_reject", "stage": 3,
            }},
        ],
    }


# ─── Stage 3b: RD Self-Test Result ──────────────────────

def stage3b_result_card() -> dict:
    """Stage 3b: RD fills self-test result + approval decision.
    Second phase — after development, report results and decide."""
    body = [
        {"type": "TextBlock", "text": "🧪 Stage 3b: Self-Test Result",
         "weight": "Bolder", "size": "Large", "wrap": True},
        {"type": "TextBlock", "text": "**Development complete. Report self-test results.**",
         "wrap": True, "spacing": "Small", "size": "Small", "color": "Accent"},
        {"type": "Input.ChoiceSet", "id": "scenario_test", "label": "🧪 Customer Scenario Self-Test Result",
         "style": "expanded", "isRequired": True,
         "choices": [
             {"title": "✅ Passed — All scenarios run correctly", "value": "pass"},
             {"title": "⚠️ Partial — Some scenarios need fixing", "value": "partial"},
             {"title": "❌ Failed — Scenarios not executed or broken", "value": "fail"},
         ]},
        {"type": "Input.Text", "id": "test_note", "label": "📝 Self-Test Notes (optional)",
         "placeholder": "e.g. Tested with 50 sample images, 94% accuracy",
         "isMultiline": True},
        {"type": "Input.ChoiceSet", "id": "approval_result", "label": "📋 Approval Decision",
         "style": "expanded", "isRequired": True,
         "choices": [
             {"title": "✅ Approved", "value": "approve"},
             {"title": "❌ Rejected", "value": "reject"},
             {"title": "⏸️ Deferred", "value": "defer"},
             {"title": "↗️ Delegated", "value": "delegate"},
         ]},
        {"type": "Input.Text", "id": "approval_note", "label": "📝 Approval Note (required if rejected/deferred/delegated)",
         "placeholder": "e.g. Self-test partially passed, edge cases need fixing",
         "isMultiline": True},
        {"type": "Input.Text", "id": "next_person", "label": "👤 Next Owner (Release Approver)",
         "placeholder": "e.g. Wang Wu", "value": "Jacky", "isRequired": True},
    ]
    return {
        "type": "AdaptiveCard", "version": "1.5",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "body": body,
        "actions": [
            {"type": "Action.Submit", "title": "✅ Submit → Stage 4 (Release Review)", "data": {
                "action": "stage3_submit", "stage": 3,
            }},
            {"type": "Action.Submit", "title": "↩️ Back to Estimate", "data": {
                "action": "stage3_back", "stage": 3,
            }},
        ],
    }


# ─── Stage 4: Release Review Editable Form ────────────────

def stage4_release_card(
    schema4: dict = None,
    release_value: str = "",
) -> dict:
    """Stage 4: Release review editable form.
    AI pre-judges, release reviewer fills form, HARD GATE on scenario_verified."""
    schema4 = schema4 or {}
    body = [
        {"type": "TextBlock", "text": "🚀 Stage 4: Release Review",
         "weight": "Bolder", "size": "Large", "wrap": True},
    ]
    if schema4.get("release_verdict"):
        body.append({"type": "TextBlock",
                     "text": f"**AI Pre-assessment**: {schema4.get('release_verdict','—')}",
                     "wrap": True, "spacing": "Small", "size": "Small", "color": "Accent"})
    body += [
        {"type": "TextBlock", "text": "⚠️ **HARD GATE**: If 'Customer Scenario Verified' is **No**, release is BLOCKED — cannot proceed.",
         "wrap": True, "spacing": "Medium", "weight": "Bolder", "color": "Attention"},
        {"type": "Input.Text", "id": "release_value", "label": "💎 Core Release Value (customer-visible change)",
         "value": release_value or "",
         "placeholder": "e.g. QC operators can auto-classify defect photos in <2s, eliminating 30s manual bottleneck",
         "isMultiline": True, "isRequired": True},
        {"type": "Input.Text", "id": "version", "label": "🏷️ Version Number",
         "placeholder": "v1.0.0", "isRequired": True},
        {"type": "Input.Date", "id": "release_date", "label": "📅 Planned Release Date",
         "isRequired": True},
        {"type": "Input.ChoiceSet", "id": "scenario_verified", "label": "🔒 Customer Scenario Verified? (HARD GATE)",
         "style": "expanded", "isRequired": True,
         "choices": [
             {"title": "✅ Yes — All customer scenarios verified", "value": "yes"},
             {"title": "❌ No — Scenarios NOT verified (will BLOCK release)", "value": "no"},
         ]},
        {"type": "Input.ChoiceSet", "id": "release_risk", "label": "⚠️ Release Risk",
         "style": "expanded", "isRequired": True,
         "choices": [
             {"title": "🟢 Low — Routine release", "value": "low"},
             {"title": "🟡 Medium — Some risk, mitigation in place", "value": "medium"},
             {"title": "🔴 High — Significant risk", "value": "high"},
         ]},
        {"type": "Input.Text", "id": "rollback_plan", "label": "🔄 Rollback Plan (optional)",
         "placeholder": "e.g. Revert to manual classification via MES fallback endpoint",
         "isMultiline": True},
        {"type": "Input.ChoiceSet", "id": "approval_result", "label": "📋 Approval Decision",
         "style": "expanded", "isRequired": True,
         "choices": [
             {"title": "✅ Approved", "value": "approve"},
             {"title": "❌ Rejected", "value": "reject"},
             {"title": "⏸️ Deferred", "value": "defer"},
             {"title": "↗️ Delegated", "value": "delegate"},
         ]},
        {"type": "Input.Text", "id": "approval_note", "label": "📝 Approval Note (required if rejected/deferred/delegated)",
         "placeholder": "e.g. Customer scenario tests not fully passed, edge cases needed",
         "isMultiline": True},
        {"type": "Input.Text", "id": "next_person", "label": "👤 Next Owner (After-sales)",
         "placeholder": "e.g. Zhao Liu", "value": "Jacky", "isRequired": True},
    ]
    return {
        "type": "AdaptiveCard", "version": "1.5",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "body": body,
        "actions": [
            {"type": "Action.Submit", "title": "🚀 Confirm Release → Stage 5", "data": {
                "action": "stage4_submit", "stage": 4,
            }},
        ],
    }


def scenario_test_card_interactive(schema3: dict) -> dict:
    """Stage 3 card with Continue button."""
    return _add_actions(scenario_test_card(schema3), [
        {"type": "Action.Submit", "title": "▶️ Continue to Release Review", "data": {
            "action": "next", "stage": 3,
        }},
    ])


def release_review_card_interactive(schema4: dict) -> dict:
    """Stage 4 card: if approved → Continue; if blocked → Stop."""
    verdict = schema4.get("release_verdict", "")
    if verdict == "approved":
        return _add_actions(release_review_card(schema4), [
            {"type": "Action.Submit", "title": "▶️ Continue to Feedback Analysis", "data": {
                "action": "next", "stage": 4,
            }},
        ])
    else:
        return _add_actions(release_review_card(schema4), [
            {"type": "Action.Submit", "title": "🛑 Stop Pipeline", "data": {
                "action": "stop", "stage": 4,
            }},
        ])


def feedback_analysis_card_interactive(schema5: dict) -> dict:
    """Stage 5 card with Continue button."""
    return _add_actions(feedback_analysis_card(schema5), [
        {"type": "Action.Submit", "title": "▶️ Continue to Process Analysis", "data": {
            "action": "next", "stage": 5,
        }},
    ])


def process_analysis_card_interactive(schema6: dict) -> dict:
    """Stage 6 final card — no buttons needed, pipeline complete."""
    return _add_actions(process_analysis_card(schema6), [
        {"type": "Action.Submit", "title": "🏁 Finish", "data": {
            "action": "finish", "stage": 6,
        }},
    ])


# ─── Feedback Capture Card (Self-Improvement Loop) ──────

def feedback_capture_card(stage: int, action: str, req_id: str = "") -> dict:
    """Card shown when user rejects/sends-back: captures the reason for Foundry IQ.
    This is the self-improvement loop entry point — human feedback becomes
    organizational knowledge so the system gets smarter over time."""
    body = [
        {"type": "TextBlock", "text": "📝 Capture Feedback — Make the System Smarter",
         "weight": "Bolder", "size": "Large", "wrap": True},
        {"type": "TextBlock", "text": f"**Stage {stage}**  |  **Action**: {action}  |  **ID**: {req_id}",
         "wrap": True, "spacing": "Small", "size": "Small", "color": "Accent"},
        {"type": "TextBlock", "text": "Your feedback will be written to **Foundry IQ** so future requirements "
         "can learn from this decision. This is the self-improvement loop.",
         "wrap": True, "spacing": "Medium"},
        {"type": "Input.Text", "id": "feedback_reason", "label": "💡 Why was this rejected / sent back?",
         "placeholder": "e.g. Missing factory lighting conditions in acceptance criteria",
         "isMultiline": True, "isRequired": True},
        {"type": "Input.Text", "id": "feedback_lesson", "label": "🔧 What should future requirements do differently?",
         "placeholder": "e.g. Always include environmental conditions as a test criterion",
         "isMultiline": True},
    ]
    return {
        "type": "AdaptiveCard", "version": "1.5",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "body": body,
        "actions": [
            {"type": "Action.Submit", "title": "✅ Submit Feedback → Foundry IQ", "data": {
                "action": "feedback_submit", "stage": stage,
                "original_action": action, "req_id": req_id,
            }},
            {"type": "Action.Submit", "title": "⏭️ Skip — Don't Save", "data": {
                "action": "feedback_skip", "stage": stage,
            }},
        ],
    }


# ─── Stage 5a: Survey Design Card ──────────────────────

def stage5a_survey_card(questions: str = "", req_id: str = "") -> dict:
    body = [
        {"type": "TextBlock", "text": "📊 Stage 5a: Customer Feedback Survey",
         "weight": "Bolder", "size": "Large", "wrap": True},
        {"type": "TextBlock", "text": f"**Requirement**: {req_id}",
         "wrap": True, "spacing": "Small", "size": "Small", "color": "Accent"},
        {"type": "TextBlock", "text": "**AI generated survey questions. Edit before publishing to customers.**",
         "wrap": True, "spacing": "Medium", "weight": "Bolder"},
        {"type": "Input.Text", "id": "survey_questions", "label": "📝 Survey Questions",
         "value": questions or (
             "1. How satisfied are you with the new feature? (1-5 scale)\n"
             "2. Did it solve the problem you reported?\n"
             "3. What would you improve?\n"
             "4. Any unexpected issues or performance problems?"
         ),
         "isMultiline": True, "isRequired": True},
        {"type": "Input.Text", "id": "next_person", "label": "👤 Next Owner (Feedback Team)",
         "placeholder": "e.g. After-sales team", "value": "Jacky", "isRequired": True},
    ]
    return {
        "type": "AdaptiveCard", "version": "1.5",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "body": body,
        "actions": [
            {"type": "Action.Submit", "title": "✅ Publish Survey → Collect Feedback", "data": {
                "action": "stage5a_submit", "stage": 5,
            }},
        ],
    }


# ─── Stage 5b: Feedback Input Card ─────────────────────

def stage5b_feedback_card(req_id: str = "") -> dict:
    body = [
        {"type": "TextBlock", "text": "📊 Stage 5b: Customer Feedback Analysis",
         "weight": "Bolder", "size": "Large", "wrap": True},
        {"type": "TextBlock", "text": f"**Requirement**: {req_id}",
         "wrap": True, "spacing": "Small", "size": "Small", "color": "Accent"},
        {"type": "TextBlock", "text": "**Paste customer feedback (CSV or text). AI analyzes and writes to Foundry IQ.**",
         "wrap": True, "spacing": "Medium", "weight": "Bolder"},
        {"type": "Input.Text", "id": "feedback_data", "label": "📋 Customer Feedback Data",
         "placeholder": (
             "customer,rating,comment\n"
             "AutoCorp,3,Works but slow with large batches\n"
             "PartsPro,5,Saved QC team 2 hours/day\n"
             "MegaFactory,2,Crashes with >100 photos"
         ),
         "isMultiline": True, "isRequired": True},
    ]
    return {
        "type": "AdaptiveCard", "version": "1.5",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "body": body,
        "actions": [
            {"type": "Action.Submit", "title": "🔍 AI Analyze → Write to Foundry IQ", "data": {
                "action": "stage5b_analyze", "stage": 5,
            }},
        ],
    }


# ─── Stage 5c: Analysis Result Card ─────────────────────

def stage5c_result_card(
    req_id: str = "",
    complaint_clusters: str = "",
    customer_health: str = "",
    insights: str = "",
) -> dict:
    body = [
        {"type": "TextBlock", "text": "📊 Stage 5: Feedback Analysis Complete",
         "weight": "Bolder", "size": "Large", "wrap": True},
        {"type": "TextBlock", "text": f"**Requirement**: {req_id}  |  **Results written to Foundry IQ**",
         "wrap": True, "spacing": "Small", "size": "Small", "color": "Accent"},
    ]
    if complaint_clusters:
        body.append({"type": "TextBlock", "text": "**Complaint Clusters:**",
                     "weight": "Bolder", "spacing": "Medium"})
        body.append({"type": "TextBlock", "text": complaint_clusters, "wrap": True})
    if customer_health:
        body.append({"type": "TextBlock", "text": "**Customer Health:**",
                     "weight": "Bolder", "spacing": "Medium"})
        body.append({"type": "TextBlock", "text": customer_health, "wrap": True})
    if insights:
        body.append({"type": "TextBlock", "text": "**Key Insights → Foundry IQ:**",
                     "weight": "Bolder", "spacing": "Medium"})
        body.append({"type": "TextBlock", "text": insights, "wrap": True})
    return {
        "type": "AdaptiveCard", "version": "1.5",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "body": body,
        "actions": [
            {"type": "Action.Submit", "title": "▶️ Continue to Stage 6 (Process Analysis)", "data": {
                "action": "stage5_continue", "stage": 5,
            }},
        ],
    }


# ─── Rollback Notice Card ──────────────────────────────

def rollback_notice_card(
    from_stage: int, to_stage: int, reason: str = "", req_id: str = "", rework: int = 1
) -> dict:
    """Card shown when a stage is rejected — notifies the previous stage's owner
    with retry/escalate options. Rework counter is tracked in Foundry IQ."""
    body = [
        {"type": "TextBlock", "text": f"↩️ Rollback — Stage {from_stage} → Stage {to_stage}",
         "weight": "Bolder", "size": "Large", "wrap": True},
        {"type": "TextBlock", "text": f"**Requirement**: {req_id}  |  **Rework #{rework}**",
         "wrap": True, "spacing": "Small", "size": "Small", "color": "Accent"},
        {"type": "TextBlock", "text": f"**Reason**: {reason or 'Not specified'}",
         "wrap": True, "spacing": "Medium", "color": "Attention"},
        {"type": "TextBlock", "text": "The requirement has been sent back. What would you like to do?",
         "wrap": True, "spacing": "Medium"},
    ]
    return {
        "type": "AdaptiveCard", "version": "1.5",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "body": body,
        "actions": [
            {"type": "Action.Submit", "title": "🔄 Modify & Resubmit", "data": {
                "action": f"rollback_retry", "stage": to_stage,
                "from_stage": from_stage, "req_id": req_id, "rework": rework,
            }},
            {"type": "Action.Submit", "title": "⬆️ Escalate Further Up", "data": {
                "action": "rollback_escalate", "stage": to_stage,
                "from_stage": from_stage, "req_id": req_id, "rework": rework,
            }},
            {"type": "Action.Submit", "title": "🏳️ Abandon Requirement", "data": {
                "action": "rollback_abandon", "stage": to_stage,
                "req_id": req_id,
            }},
        ],
    }
