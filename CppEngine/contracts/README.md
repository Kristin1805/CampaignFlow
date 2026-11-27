# cf_engine JSON contract (Django ↔ C++)

- Input: [`contracts/optimize.input.schema.json`](optimize.input.schema.json),
  example: [`contracts/examples/black-friday.input.json`](examples/black-friday.input.json)
- Output: [`contracts/optimize.output.schema.json`](optimize.output.schema.json)

What Django does before sending:

- All ids are UUID strings.
- `priority`: `low` → 1, `medium` → 2, `high` → 3, `urgent` → 4.
- Tasks with status `completed` or `cancelled` are not sent.
- `deadline` = `Campaign.launch_at`.
- `calendar.work_days` uses Django's numbering: 0 = Monday … 6 = Sunday.
- `skill: null` means anyone can do the task.

What the engine checks itself (exit 3): unique task ids, every `depends_on.task_id`
exists, `deadline` > `now`. Cycles → exit 2.

In the output, `changes[]` lists every proposed assignee change, including
assigning a task that had no assignee (`"from": null`). Nothing is applied until
the manager clicks Apply in Django.
