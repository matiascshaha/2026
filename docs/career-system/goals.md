# Goals and user needs

The system should reduce repeated work in finding suitable opportunities and
preparing accurate applications, while keeping the owner able to inspect and
control what is sent.

## User goals

- **G1 Find suitable opportunities.** Use the job radar for discovery and revisit
  previous recommendations. A recommendation is a lead, not proof of an application.
- **G2 Reuse accurate career context.** Maintain one source of career facts,
  achievements, wording preferences, and profile links. Use it to answer questions
  and prepare materials without repeatedly collecting the same information.
- **G3 Produce tailored materials.** Create role-specific resumes, cover letters,
  and freeform application answers supported by actual experience.
- **G4 Keep career information current.** Support owner-confirmed brag-sheet
  additions, career corrections, and profile updates without inventing facts.
- **G5 Understand every application.** Show the job, source evidence, material
  versions, important drafting choices, edits, authorization, and final outcome.
- **G6 Reduce manual effort safely.** Start with assisted applications, then enable
  only a defined, verified scope of automation. Handle unknowns and exceptions
  without making unsupported claims or sending duplicate applications.

## Scope

The context repository is a reusable knowledge layer and application toolkit. It
is useful even without a job radar. Discovery remains the radar's responsibility.
The proposed coordinator selects a lead, retrieves relevant context, builds a
packet, records the process, and performs only authorized actions.

This phase documents goals, requirements, and design. It does not build the
coordinator, migrate the radar, choose a hosted database, enable autopilot, or
submit applications. Detailed personal job filters and any future submission
permissions are private configuration, not public design examples.

## Success signals

The owner can find relevant evidence without restating their history, receive a
usable role-specific packet, and understand the status of an application without
searching several conversations. Historical leads can be reviewed without being
mistaken for submissions. A submitted packet can be reconstructed from its saved
versions and evidence, and uncertain outcomes remain visible.

Baseline measures and targets for preparation time, correction rate, audit
completeness, and duplicate prevention can be agreed when the assisted workflow
starts. No numerical service level or application quota is assumed here.
