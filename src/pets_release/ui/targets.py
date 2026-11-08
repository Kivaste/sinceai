"""Project policy thresholds against existing measurements; never invent a missing measurement."""
from pets_release.ladders import at_least_as_coarse
from pets_release.policy import get_policy
from pets_release.run.purpose import THRESHOLD


def target_rows(scenario, manifest=None, person_k=None):
    policy = get_policy(scenario)
    manifest = manifest or {}
    measured = manifest.get("measured", {})
    tasks = {t["task"]: t for t in measured.get("utility", {}).get("tasks", [])}
    fields = {(f["table"], f["column"]): f for f in manifest.get("fieldJustifications", [])}
    records = {c["check"]: c for c in manifest.get("gate", {}).get("checks", [])}
    rows = []

    def add(name, threshold, value=None, passes=None, status=None):
        if status is None:
            status = "not measured" if value is None or passes is None else ("met" if passes else "not met")
        rows.append({"name": name, "threshold": threshold, "measured": value, "status": status})

    for target in policy.privacy_targets:
        kind = target["kind"]
        if kind == "k_anonymity":
            # person_k comes only from the verified manifest (ui.jobs.person_k).
            pk = person_k or {}
            below, minimum, k = pk.get("belowK"), pk.get("minK"), pk.get("k")
            if below is None or k is None or k < target["k"]:
                add(target["id"], f">= {target['k']}")
            elif minimum is not None:
                add(target["id"], f">= {target['k']}", minimum, minimum >= target["k"] and below == 0)
            else:
                add(target["id"], f">= {target['k']}", f"{below} persons below k={k}", below == 0)
        elif kind == "text_recall":
            labels = {r["label"]: r for r in measured.get("redaction", {}).get("labels", [])}
            for label in target["labels"]:
                entry = labels.get(label, {})
                value = entry.get("recall") if entry.get("support", 0) > 0 else None
                add(f"{target['id']} {label}", f">= {target['min']}", value,
                    None if value is None else value >= target["min"])
        elif kind == "health_in_text":
            record = records.get("text.health", {})
            threshold = f"hits <= {target['max_hits']}"
            if record.get("status") == "not_applicable":
                add(target["id"], threshold, status="not applicable")
            else:
                # A failed check is measured: show its hits as not met. error/not_run stay unknown.
                value = record.get("hits") if record.get("status") in ("pass", "fail") else None
                add(target["id"], threshold, value,
                    None if value is None else record["status"] == "pass" and value <= target["max_hits"])
        elif kind == "timestamp_floor":
            timestamps = [f for key, f in fields.items() if policy.floors[key].family == "timestamp"
                          and f["decision"] == "released"]
            value = ", ".join(sorted({f["rung"] for f in timestamps})) or None
            add(target["id"], target["rung"] + " or coarser", value,
                None if value is None else all(at_least_as_coarse(f["rung"], target["rung"]) for f in timestamps))
    for key, floor in sorted(policy.floors.items()):
        field = fields.get(key)
        value = None if field is None else field["rung"]
        add(".".join(key), floor.rung + " or coarser", value,
            None if value is None else at_least_as_coarse(value, floor.rung))
    for check in policy.purpose_checks:
        task = tasks.get(check, {})
        value = task.get("after") if task.get("status") == "ok" else None
        add(check, f">= {THRESHOLD}", value, None if value is None else value >= THRESHOLD)
    adopted = {s["check"] for s in manifest.get("sacrifices", [])}
    for sacrifice in policy.sacrifices:
        task = tasks.get(sacrifice["check"], {})
        value = task.get("after") if task.get("status") == "ok" else None
        floor = sacrifice["floor_score"]
        name = sacrifice["check"] + " sacrifice floor"
        if value is None:
            add(name, f">= {floor}")
        elif sacrifice["check"] not in adopted:
            # No recorded sacrifice: the original threshold row above is the only target.
            add(name, f">= {floor}", value, status="not adopted")
        else:
            # A floor is never the original target met (docs/story/06): label it as accepted.
            add(name, f">= {floor}", value, status="accepted sacrifice" if value >= floor else "not met")
    return rows
