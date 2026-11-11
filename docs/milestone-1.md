# Milestone 1 — Understand & Establish the Baseline

> **Understand before you redesign.**

## 1. Team & Store

- **Team members:**
- **Store name:**
- **Store vertical / concept:**
- **Repository:**
- **Short product description:**

## 2. Baseline Validation

Briefly record the evidence that your team verified the starter system before redesigning it.

- [ ] Application runs from a clean setup.
- [ ] Existing automated tests pass locally.
- [ ] GitHub Actions CI passes.
- [ ] Catalog → cart → checkout → order flow works end-to-end.
- [ ] Orders and inventory changes persist after restarting the app.

Add only the compact evidence needed to make these claims reviewable. Do not fill this document with screenshots.

## 3. Current System Design

Add one simple diagram of the system **as it exists now**. Show the major parts, the important dependencies between them, persistence, and the payment dependency.

You may use Mermaid, UML, or another diagramming tool. Accuracy matters more than visual polish.

## 4. Responsibilities & Dependencies

| Part / module | Main responsibility | Important dependencies |
|---|---|---|
| | | |
| | | |
| | | |

Then trace the main purchase flow from the browser request through order persistence in a short paragraph or numbered sequence.

## 5. Design Observations

Record 3–5 evidence-based observations about the baseline. Include all of the following somewhere in the set:

- at least one current design strength;
- at least one original decision that is reasonable for the current problem;
- at least one coupling or design-pressure concern;
- at least one potential technical-debt concern;
- a clear distinction between **what you observe now** and redesign you might consider only if future requirements justify it.

Do **not** add patterns, layers, interfaces, repositories, factories, or architectural abstractions just in case they might become useful later.

## 6. AI Use

If the team used AI meaningfully, list:

- tool(s) used;
- what the tool helped with;
- what the team reviewed, corrected, or validated itself.

If no AI was used, state that explicitly.
