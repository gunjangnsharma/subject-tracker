# Backup / Import JSON — blueprint

The exact shape the app's **Import JSON** feature accepts (and **Export JSON**
produces). Hand this file — or [`backup.schema.json`](backup.schema.json) — to any
tool or agent to generate a valid file. Import is at `POST /import`; export at
`GET /export`. See also BUILD_CONTEXT §10.

---

## 1. The format (annotated)

```jsonc
{
  "format": "subject-tracker-backup",          // REQUIRED, must be exactly this
  "version": 2,                                 // REQUIRED, use 2 (1 also accepted; see §4)
  "exported_at": "2026-08-01T12:00:00+00:00",   // optional, ignored on import
  "user": { "username": "alice" },              // optional, ignored on import
  "subjects": [                                 // REQUIRED array (may be empty)
    {
      "name": "Machine Learning",               // REQUIRED, non-empty string
      "modules": [                              // optional (default [])
        {
          "name": "Linear Algebra",             // REQUIRED, non-empty string
          "chapters": [                         // optional (default []); ORDER MATTERS
            {
              "title": "Vectors",               // REQUIRED, non-empty string
              "kind": "video",                  // "video" | "text" (default "video")
              "duration_minutes": 130,          // REQUIRED int >= 0  (2h 10m -> 130)
              "completed_minutes": 90,          // REQUIRED (v2) int >= 0, clamped to duration
              "plan_dates": ["2026-08-03"],     // 0 or 1 date; extras dropped
              "activity": [                     // optional; per-day study log
                { "occurred_on": "2026-08-01", "minutes_delta": 90.0 }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

## 2. Field reference & rules

| Field | Type | Required | Rules |
|---|---|---|---|
| `format` | string | yes | must equal `"subject-tracker-backup"` |
| `version` | integer | yes | `2` (recommended) or `1` |
| `exported_at` | string | no | ISO-8601; ignored on import |
| `user.username` | string | no | ignored on import |
| `subjects` | array | yes | may be empty |
| `subject.name` | string | yes | non-empty (trimmed) |
| `subject.modules` | array | no | default `[]` |
| `module.name` | string | yes | non-empty |
| `module.chapters` | array | no | default `[]`. **Array order = display order** (see §3) |
| `chapter.title` | string | yes | non-empty |
| `chapter.kind` | string | no | `"video"` or `"text"`; default `"video"` |
| `chapter.duration_minutes` | integer | yes | `>= 0`. **Minutes, not "Xh Ym"** (130 = 2h 10m) |
| `chapter.completed_minutes` | integer | yes (v2) | `>= 0`; clamped to `0..duration_minutes` |
| `chapter.plan_dates` | array<string> | no | `"YYYY-MM-DD"`; **only the first is used** |
| `chapter.activity` | array | no | see below |
| `activity[].occurred_on` | string | yes (if present) | `"YYYY-MM-DD"` |
| `activity[].minutes_delta` | number | yes (if present) | +/- minutes changed that day |

## 3. Importer behavior (must know)

- **Whole minutes everywhere** — never `"1h 30m"`. `duration_minutes` /
  `completed_minutes` are integers; `minutes_delta` is a number.
- **Chapter order travels as array order.** There is **no `position` field** —
  the order of each module's `chapters` array *is* the order the user sees, and
  import assigns positions by walking the array. So list chapters in the order
  you want them displayed; a re-export reproduces it exactly. (A `position` key
  in your file is simply ignored.) Users can then reorder chapters in the UI with
  the ▲/▼ buttons on the subject page.
- **Additive** — creates *new* subjects; does not merge into existing ones.
  Re-importing the same file duplicates its subjects.
- **Atomic** — any invalid field aborts the whole import; nothing is written.
- **One plan date per chapter** — extra `plan_dates` entries are dropped.
- **Past dates are accepted on import** (the "no back-dating" rule is UI-only).
- **Progress vs. activity are independent:** progress bars / percentages come from
  `completed_minutes`; the dashboard's "studied today / this week" comes from
  `activity` (sum of positive `minutes_delta` per day). Include `activity` if you
  want the daily study chart populated; `completed_minutes` alone still drives all
  the roll-ups. The importer never fabricates activity from `completed_minutes`.
- **Rejected:** non-object root, wrong `format`, `version` other than 1/2, `subjects`
  not a list, empty required strings, non-integer numbers, `kind` other than
  video/text, malformed dates.

## 4. Versions

- **v2** (generate this): chapters carry `completed_minutes`.
- **v1** (legacy): chapters carried `completion` (integer 0–10). Still importable —
  the importer converts `completed_minutes = round(duration_minutes * completion / 10)`.

## 5. Ready-to-paste prompt for another agent

> Generate a JSON file for the "subject-tracker-backup" import format (version 2).
> Root object: `"format": "subject-tracker-backup"`, `"version": 2`, and `"subjects"`
> — an array of `{ "name", "modules": [ { "name", "chapters": [ … ] } ] }`.
> Each chapter is `{ "title", "kind": "video"|"text", "duration_minutes": <int minutes>,
> "completed_minutes": <int minutes, 0..duration>, "plan_dates": ["YYYY-MM-DD"] (0 or 1),
> "activity": [ { "occurred_on": "YYYY-MM-DD", "minutes_delta": <number> } ] }`.
> Rules: all times are whole minutes (2h 10m = 130), never "Xh Ym"; `completed_minutes`
> ≤ `duration_minutes`; at most one `plan_dates` entry; list each module's chapters in
> the order they should appear (array order is the display order — there is no
> `position` field); `activity.minutes_delta` should
> sum to that chapter's `completed_minutes` across the study dates. Output ONLY valid
> JSON, no comments.

## 6. Minimal valid file

```json
{ "format": "subject-tracker-backup", "version": 2,
  "subjects": [ { "name": "My Subject", "modules": [] } ] }
```

## 7. Validate before importing

```bash
python -c "import json,jsonschema,sys; jsonschema.validate(json.load(open('mybackup.json')), json.load(open('docs/backup.schema.json'))); print('valid')"
```
(`pip install jsonschema` first. This is just an optional external check — the app
validates on import regardless.)
