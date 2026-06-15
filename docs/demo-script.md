# IQ Relay — Demo Script (5 min)

> **Format:**
> - `[ACTION]` = what you do on screen (don't say out loud)
> - *Italic* = what you say
> - `// tip` = delivery note

---

## SEGMENT 1 — HOOK (0:00–0:45)

`[Screen: empty Web Chat input]`

> *"Let me start with a question."*
> *"When your best engineer resigns — where does their knowledge go?"*

`// Pause 1 second`

> *"Most teams would say: nowhere. It walks out the door with them."*
> *"IQ Relay is built to change that."*

`[Type: ?customer feedback survey — hit Enter]`

`// Stay silent while results load`

`[Foundry IQ result card appears]`

> *"This is a knowledge record left by Sarah Chen — our former after-sales lead.*
> *She spent six months figuring out why customers weren't filling in post-service surveys.*
> *She cracked it. And then she resigned."*

`// Pause 1 second — let the viewer read the card`

> *"But her knowledge is still here.*
> *Three pitfalls, documented.*
> *Don't send surveys right after service closes.*
> *Cut to three questions.*
> *Embed Microsoft Forms directly in a Teams message.*
> *A new hire finds this in ten seconds."*

---

## SEGMENT 2 — WHAT IS IQ RELAY (0:45–1:00)

> *"IQ Relay has two sides.*
> *Relay: a six-agent AI pipeline that routes every requirement through six stages —*
> *Gatekeeping, PM Review, R&D, Release, Feedback, and Retrospective.*
> *IQ: every decision, every rejection, every lesson — written to Foundry IQ automatically.*
> *So the next team inherits the knowledge of everyone who came before them.*
> *Let me show you both."*

---

## SEGMENT 3 — SUBMIT REQUIREMENT (1:00–1:25)

`[Paste requirement:]`

```
The front-desk receptionist at our hotel needs the service robot to respond
within 5 seconds during guest check-in, because robots currently take over
20 seconds which annoys guests and increases complaints.
```

`[Foundry IQ Alert card appears]`

> *"Before Stage 1 even starts —*
> *the system found a similar case from last year.*
> *A hotel kiosk incident."*

`// Point at the pitfall on the card`

> *"The pitfall: the vendor blamed network latency.*
> *The real cause was a synchronous API lock.*
> *This team now knows to profile the full call chain first.*
> *That's IQ Relay preventing a known mistake before it happens again."*

---

## SEGMENT 4 — S1 GATEKEEPING (1:25–1:55)

`[Stage 1 editable card appears]`

> *"Stage 1 — Gatekeeper.*
> *The AI extracted four structured fields from that one sentence.*
> *Who needs it, the scenario, the problem, and the expected outcome."*

`[Edit the Expected Outcome field — add "during peak check-in hours"]`

> *"I can edit any field before confirming.*
> *Here I'll refine the expected outcome."*

`[Click: Confirm & Continue]`

---

## SEGMENT 5 — S2 PM REVIEW (1:55–2:15)

`// LLM is running — talk while waiting`

> *"Stage 2 — Value Transform.*
> *While the AI generates acceptance criteria and test cases..."*

`[S2 card appears]`

> *"...the PM reviews, adjusts priority and success metrics,*
> *then passes it to engineering."*

`[Click: Confirm]`

---

## SEGMENT 6 — S3 ROLLBACK + KNOWLEDGE WRITTEN LIVE (2:15–3:10)`

`[S3a card appears]`

> *"Stage 3 — R&D Estimate.*
> *I'm going to deliberately send this back.*
> *Maybe the acceptance criteria were unclear."*

`[Fill in a field briefly, then click: Send Back to PM]`

`[Feedback capture card appears]`

> *"The system asks why.*
> *Watch what happens to this rejection reason —*
> *it doesn't just disappear."*

`[Fill: "Acceptance criteria missing edge case for concurrent check-in requests", click: Submit Feedback]`

`// Pause — let the "written to Foundry IQ" message appear`

> *"Written to Foundry IQ. Immediately.*
> *Not after the project closes. Not in a retrospective document nobody reads.*
> *Right now, while the context is fresh."*

`[Rollback notice card appears]`

`// Point at "Why it was sent back" section`

> *"The PM sees exactly why it came back — Rework count: 1.*
> *They can retry, escalate, or abandon."*

`[Click: Modify & Resubmit → re-confirm S2 → confirm S3]`

---

## SEGMENT 7 — S4 HARD GATE (3:10–3:40)

`[S4 card appears]`

> *"Stage 4 — Release Review.*
> *I'm going to try submitting without verifying the scenario."*

`[Leave scenario_verified unchecked — click Submit]`

`// Pause — let the block message appear`

> *"Blocked."*

`// Pause 1 second`

> *"This is a hard gate enforced in code.*
> *Not a warning. Not a checkbox you can skip.*
> *The requirement cannot go to production*
> *until the scenario is actually tested.*
> *No exceptions."*

`[Check scenario_verified — resubmit]`

> *"Now it passes."*

---

## SEGMENT 8 — SELF-IMPROVING LOOP (3:40–4:20)

`// Narrate over S5/S6 — speed up waiting with FFmpeg`

> *"Stage 5 collects customer feedback.*
> *Stage 6 — the retrospective — analyzes the full pipeline run*
> *and writes structured lessons back to Foundry IQ."*

`[After S6 completes, paste new requirement:]`

```
The hotel concierge app needs to show room availability in real time —
the current 30-second delay is causing double-booking incidents.
```

`[Foundry IQ Alert appears — matches the S3 rejection we just wrote]`

`// Point at the matched entry`

> *"Different requirement. Same hotel domain.*
> *The alert already knows:*
> *a similar requirement was just sent back at Stage 3 —*
> *acceptance criteria missing edge case for concurrent requests.*
> *The system remembered.*
> *We didn't ask it to.*
> *We didn't train it.*
> *It just remembered — because that's what IQ Relay does."*

---

## SEGMENT 9 — CLOSING (4:20–4:45)

> *"Six AI agents. Human verification at every stage.*
> *A rollback chain that captures every rejection and writes it to organizational memory.*
> *A hard gate that enforces quality in code, not in policy.*
> *A knowledge base that grows with every run —*
> *so your team never learns the same lesson twice."*

`// Pause`

> *"The engineers who figured this out before you —*
> *even if they've left —*
> *they're still here."*

`// Pause 1 second`

> *"IQ Relay."*

---

## Delivery Tips

| Moment | What to do |
|---|---|
| While typing | Stay silent — let the action speak |
| Waiting for AI | Say one sentence about what's coming |
| Card appears | Pause 1 second before speaking |
| "Written to Foundry IQ" message | Pause — let it land — then explain |
| Before clicking Reject/Block | Say intent first: *"I'm going to deliberately..."* |
| "Blocked." | Say it — pause 1 second — then explain |
| Rollback card | Point at specific fields, don't read every word |
| S3 rejection → new requirement alert | This is the money moment — slow down here |

---

## FFmpeg Speed-Up Reference

```bash
# Speed up S5/S6 wait (e.g. seconds 200-240) by 10x
ffmpeg -i input.mov \
  -filter_complex "\
    [0:v]trim=0:200,setpts=PTS-STARTPTS[v1];\
    [0:v]trim=200:240,setpts=(PTS-STARTPTS)/10[v2];\
    [0:v]trim=240:9999,setpts=PTS-STARTPTS[v3];\
    [0:a]atrim=0:200,asetpts=PTS-STARTPTS[a1];\
    [0:a]atrim=200:240,asetpts=(PTS-STARTPTS)/10,volume=0[a2];\
    [0:a]atrim=240:9999,asetpts=PTS-STARTPTS[a3];\
    [v1][v2][v3]concat=n=3:v=1:a=0[v];\
    [a1][a2][a3]concat=n=3:v=0:a=1[a]" \
  -map "[v]" -map "[a]" output.mp4
```

> Replace `200` / `240` with actual timestamps after recording.
> `volume=0` mutes the sped-up segment.
