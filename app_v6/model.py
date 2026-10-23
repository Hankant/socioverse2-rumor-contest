"""V4 native SocioVerse2 providers. Scientific inputs: the user's four V4 files.

The rule contract is explicitly ENGINEERING ONLY until confirmed. No LLM fallback.
Core is reused unchanged; environment owns memories so action replay restores them.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import os
import tempfile
import time
from collections import Counter
from pathlib import Path
from statistics import mean

import numpy as np
from socioverse.abc import PopulationProvider, EnvironmentProvider, DecisionModel, MetricCollector
from socioverse.engine import register
from socioverse.schemas import Persona, Observation, Action

NETWORK_FEED_POLICY = "network_rumor_all_comments_v1"
from comment_policy import LATEST_FEED_POLICY,PARTICIPATION_POLICY,MEMORY_POLICY,recent_comments,personal_memory_posts
from memory_policy import ROLLING, retained_memory, validate_memory_policy
NETWORK_FEED_POLICIES = frozenset((NETWORK_FEED_POLICY,LATEST_FEED_POLICY))
FULL_THREAD_POLICIES = frozenset(("shared_rumor_all_comments_v1", *NETWORK_FEED_POLICIES))


def feed_description(policy, comment_window_limit=100):
    return {
        NETWORK_FEED_POLICY: "关注SOURCE者初始接触谣言；其他人通过关注者转发首次接触；已接触者每轮回看原帖及全部先前评论；官方独立账号，定向及转发触达",
        LATEST_FEED_POLICY: f"关注与转发决定首次接触；已接触者每轮回看原帖及每个主帖截至上一轮最新{comment_window_limit}条评论；官方独立账号；自愿评论，个人记忆不重放旧评论全文",
        "shared_rumor_all_comments_v1": "全体每轮同一谣言主帖及全部先前评论；官方独立账号，定向及转发触达",
        "legacy": "全部活跃，每轮最多5帖，每帖最多2评论",
    }[policy]


def retry_file(operation):
    for attempt in range(6):
        try:
            return operation()
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.2 * (attempt + 1))


def read_json(path):
    return retry_file(lambda: json.loads(Path(path).read_text(encoding="utf-8")))


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replace only after the complete JSON is flushed: interruption cannot leave half a ledger.
    # A short random sibling name avoids repeating a 64-character cache hash
    # in temporary filenames near the Windows path-length limit.
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".write-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        retry_file(lambda: os.replace(temporary, path))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = sorted(csv.DictReader(f), key=lambda r: r["agent_id"])
    assert len(rows) == 582 and len({r["agent_id"] for r in rows}) == 582
    assert Counter(r["decision_mode"] for r in rows) == {"llm": 305, "rule": 277}
    assert Counter(r["group"] for r in rows) == {"inside": 82, "outside": 500}
    return rows


def make_network(rows):
    rng = np.random.Generator(np.random.PCG64(20261018))
    edges = []
    for r in rows:
        for same, count in ((True, 8), (False, 2)):
            candidates = [p["agent_id"] for p in rows if p != r and (p["group"] == r["group"]) == same]
            edges.extend((r["agent_id"], str(j)) for j in rng.choice(candidates, count, replace=False))
        if r["group"] == "inside":
            edges.append((r["agent_id"], "SOURCE"))
    return edges


def targets(rows, strategy="inside"):
    pool = [r["agent_id"] for r in rows if strategy == "random" or r["group"] == strategy]
    rng = np.random.Generator(np.random.PCG64(20261019))
    return sorted(map(str, rng.choice(pool, min(40, len(pool)), replace=False)))


@register("population", "rumor_v6.population")
class V4Population(PopulationProvider):
    def __init__(self, bundle):
        self.bundle = bundle
        self.rows = load_rows(bundle.provider_args["roster_csv"])
        self.edges = bundle.interaction.edges

    def build(self, seed):
        return [Persona(agent_id=r["agent_id"], group_key=r["group"], attributes=r,
                        init_state={"current_belief": "unjudged"}) for r in self.rows]

    def neighbors(self, aid):
        return [b for a, b in self.edges if a == aid]


@register("environment", "rumor_v6.environment")
class V4Environment(EnvironmentProvider):
    def __init__(self, bundle):
        self.bundle = bundle
        self.cfg = bundle.provider_args
        validate_memory_policy(self.cfg)
        self.rows = load_rows(self.cfg["roster_csv"])
        self.by_id = {r["agent_id"]: r for r in self.rows}
        self.following = {a: set() for a in self.by_id}
        for a, b in self.cfg["edges"]:
            self.following[a].add(b)
        self.direct_targets = self.cfg["direct_targets"]
        self.government_tick = self.cfg.get("government_tick", 20)

    def reset(self, seed):
        self.t = 0
        self.offline = {}
        self.beliefs = {a: "unjudged" for a in self.by_id}
        self.credibility = {a: None for a in self.by_id}
        self.component_credibility = {a: None for a in self.by_id}
        self.condition_application = {a: None for a in self.by_id}
        self.condition_context_ref = {a: None for a in self.by_id}
        self.seen = {a: set() for a in self.by_id}
        self.reposted = {a: set() for a in self.by_id}
        self.memory = {a: [] for a in self.by_id}
        self.exposure_history = {a: {} for a in self.by_id}
        self.read_comments = {a: set() for a in self.by_id}
        self.rule_corrected = set()
        self.last_updated = {a: None for a in self.by_id}
        self.posts = {}
        self.comments = {}
        self.applied = {}
        self.cohort = set()
        self.transitions = {}
        self._publish_root("P001", "SOURCE", 0, self.cfg["rumor_text"])

    def _publish_root(self, cid, author, tick, text):
        self.posts[cid] = dict(content_id=cid, root_content_id=cid, author_id=author,
                               original_author_id=author, published_tick=tick,
                               available_tick=1 if tick == 0 else tick,
                               text=text, repost_text="")

    def advance_to(self, t):
        self.t = t
        if self.cfg.get('memory_retention_policy') == ROLLING:
            for aid in self.memory:
                self.memory[aid] = retained_memory(self.memory[aid], t, self.cfg)
        if t == self.government_tick and "G001" not in self.posts:
            self._publish_root("G001", "GOVERNMENT", self.government_tick, self.cfg["correction_text"])
        return [e for e in self.bundle.scheduled_events if e.at_step == t]

    def observe_batch(self, agent_ids, t, round_idx=0):
        if self.cfg.get("feed_policy") in FULL_THREAD_POLICIES:
            return self._observe_shared_thread(agent_ids, t)
        out = []
        for aid in agent_ids:
            eligible = [p for p in self.posts.values()
                        if p["available_tick"] <= t and 0 <= t - p["published_tick"] < 40
                        and (p["author_id"] in self.following[aid] or p["content_id"] in self.seen[aid])]
            eligible.sort(key=lambda p: (-p["published_tick"], p["content_id"]))
            fresh, revisits = [], []
            for p in eligible:
                cid = p["content_id"]
                if cid not in self.seen[aid]:
                    fresh.append(p)
                    continue
                history = self.exposure_history[aid][cid]
                visible_comments = sorted(
                    [c for c in self.comments.values() if c["target_content_id"] == cid and c["published_tick"] < t],
                    key=lambda c: (-c["published_tick"], c["comment_id"]))[:2]
                changed = any(c["author_id"] != aid and c["comment_id"] not in self.read_comments[aid]
                              for c in visible_comments)
                ticks = history.get("ticks", [history["tick"]])
                due = t - max(ticks) >= self.cfg.get("reread_interval", 3)
                if changed or (due and len(ticks) < self.cfg.get("max_post_reads", 4)):
                    revisits.append(p)
            # One old-post slot when available; up to four fresh slots. Fill unused slots.
            revisits.sort(key=lambda p: (
                max(self.exposure_history[aid][p["content_id"]].get("ticks", [0])), p["content_id"]))
            selected = fresh[:4] + revisits[:1]
            selected += (fresh[4:] + revisits[1:])[:max(0, 5-len(selected))]
            direct = t == self.government_tick and aid in self.direct_targets
            chosen = ([self.posts["G001"]] + [p for p in selected if p["content_id"] != "G001"]) if direct else selected
            feed = []
            for p in ([] if aid in self.offline else chosen[:5]):
                post = copy.deepcopy(p)
                cs = [c for c in self.comments.values() if c["target_content_id"] == p["content_id"] and c["published_tick"] < t]
                post["comments"] = sorted(cs, key=lambda c: (-c["published_tick"], c["comment_id"]))[:2]
                post["delivery"] = "direct_government" if direct and p["content_id"] == "G001" else "followee"
                post["can_repost"] = p["root_content_id"] not in self.reposted[aid]
                post["block_reason"] = None if post["can_repost"] else "duplicate_root_repost"
                post["is_reread"] = p["content_id"] in self.seen[aid]
                feed.append(post)
            out.append(Observation(agent_id=aid, step=t,
                local_physical={"persona": self.by_id[aid], "current_belief": self.beliefs[aid], "technical_offline": aid in self.offline,
                                "exposure_history": copy.deepcopy(self.exposure_history[aid]), "rule_corrected": aid in self.rule_corrected,
                                "government_trust": self.cfg.get("government_trust", {}).get(aid),
                                "source_trust": self.cfg.get("source_trust", {}).get(aid),
                                "belief_target": self.cfg.get("belief_target"),
                                "belief_measurement_policy": self.cfg.get("belief_measurement_policy", "legacy"),
                                "decision_condition_policy": self.cfg.get("decision_condition_policy", "legacy"),
                                "comment_target_policy": self.cfg.get("comment_target", "first_displayed_post"),
                                "feed_policy": self.cfg.get("feed_policy", "legacy"),
                                "subjective_credibility": self.credibility[aid],
                                "component_credibility": copy.deepcopy(self.component_credibility[aid]),
                                "memory": copy.deepcopy(retained_memory(self.memory[aid], t, self.cfg)),
                                "memory_retention_policy": self.cfg.get('memory_retention_policy', 'last_five_experiences_v1'),
                                "memory_window_ticks": self.cfg.get('memory_window_ticks'),
                                "already_reposted": sorted(self.reposted[aid])},
                local_information={"posts": feed}))
        return out

    def _observe_shared_thread(self, agent_ids, t):
        """At most one rumor root per person/tick; a separate official account.

        Reposts remain transport records. They do not become additional rumor
        reading slots. All earlier comments on a root and its reposts belong to
        that root's discussion. Official comments never merge into P001.
        """
        out = []
        for aid in agent_ids:
            feed = []
            active = aid not in self.offline and t >= 1
            if active:
                delivery = "public_shared_thread"
                if self.cfg.get("feed_policy") in NETWORK_FEED_POLICIES:
                    delivery = ("followed_source" if "SOURCE" in self.following[aid] else
                                "rumor_thread_revisit" if "P001" in self.seen[aid] else
                                "followee_rumor_repost" if self._visible_relays("P001", aid, t) else None)
                if delivery and self.posts["P001"]["available_tick"] <= t:
                    feed.append(self._shared_root_view("P001", aid, t, delivery))
                if "G001" in self.posts and self.posts["G001"]["available_tick"] <= t:
                    direct = t == self.government_tick and aid in self.direct_targets
                    relays = self._visible_relays("G001", aid, t)
                    if direct or "G001" in self.seen[aid] or relays:
                        official = self._shared_root_view("G001", aid, t,
                            "direct_government" if direct else "official_thread_or_followee_repost")
                        feed.insert(0, official) if direct else feed.append(official)
            out.append(Observation(agent_id=aid, step=t,
                local_physical={"persona": self.by_id[aid], "current_belief": self.beliefs[aid],
                    "technical_offline": aid in self.offline, "exposure_history": copy.deepcopy(self.exposure_history[aid]),
                    "rule_corrected": aid in self.rule_corrected,
                    "government_trust": self.cfg.get("government_trust", {}).get(aid),
                    "source_trust": self.cfg.get("source_trust", {}).get(aid),
                    "belief_target": self.cfg.get("belief_target"),
                    "belief_measurement_policy": self.cfg.get("belief_measurement_policy", "legacy"),
                    "decision_condition_policy": self.cfg.get("decision_condition_policy", "legacy"),
                    "comment_target_policy": self.cfg.get("comment_target", "first_displayed_post"),
                    "feed_policy": self.cfg["feed_policy"],
                    "comment_window_limit": self.cfg.get("comment_window_limit"),
                    "comment_participation_policy": self.cfg.get("comment_participation_policy","legacy"),
                    "memory_comment_policy": self.cfg.get("memory_comment_policy","complete_observed_v1"),
                    "subjective_credibility": self.credibility[aid],
                    "component_credibility": copy.deepcopy(self.component_credibility[aid]),
                    "memory": copy.deepcopy(retained_memory(self.memory[aid], t, self.cfg)),
                    "memory_retention_policy": self.cfg.get('memory_retention_policy', 'last_five_experiences_v1'),
                    "memory_window_ticks": self.cfg.get('memory_window_ticks'),
                    "already_reposted": sorted(self.reposted[aid])},
                local_information={"posts": feed}))
        return out

    def _visible_relays(self, root, aid, t):
        return [p for p in self.posts.values() if p["root_content_id"] == root and p["content_id"] != root
                and p["author_id"] in self.following[aid] and p["available_tick"] <= t
                and 0 < t-p["published_tick"] < 40]

    def _shared_root_view(self, root, aid, t, delivery):
        post = copy.deepcopy(self.posts[root])
        # Include comments by non-followed accounts and comments under any
        # repost of THIS root; preserve IDs, text, author and publication time.
        post["comments"] = sorted([copy.deepcopy(c) for c in self.comments.values()
            if c["published_tick"] < t
            and self.posts.get(c["target_content_id"], {}).get("root_content_id") == root],
            key=lambda c: (c["published_tick"], c["comment_id"]))
        if self.cfg.get("feed_policy")==LATEST_FEED_POLICY:
            post["comments"]=recent_comments(post["comments"],self.cfg["comment_window_limit"],self.cfg["comment_tie_seed"])
        post["relay_context"] = sorted([{
            k: p[k] for k in ("content_id", "author_id", "published_tick", "repost_text")}
            for p in self._visible_relays(root, aid, t)], key=lambda p: (p["published_tick"], p["content_id"]))
        post.update(delivery=delivery, can_repost=root not in self.reposted[aid],
            block_reason="duplicate_root_repost" if root in self.reposted[aid] else None,
            is_reread=root in self.seen[aid], comment_scope="all_earlier_comments_on_root_and_reposts")
        if self.cfg.get("feed_policy")==LATEST_FEED_POLICY:
            post.update(comment_scope=f"latest_{self.cfg['comment_window_limit']}_earlier_comments_per_root",
                comment_window_limit=self.cfg["comment_window_limit"],
                comment_order="newest_tick_then_seeded_hash_v1")
        return post

    def apply(self, actions):
        # Validate the entire batch BEFORE committing any agent (atomic decision stage).
        prepared = []
        for a in actions:
            key = (a.step, a.agent_id)
            signature = digest(a.payload)
            if key in self.applied:
                if self.applied[key] != signature:
                    raise ValueError("conflicting action for an already committed agent/tick")
                continue
            if a.payload.get("decision_status") == "technical_dropout":
                if a.kind != "idle" or a.step != self.t or a.agent_id not in self.by_id or self.by_id[a.agent_id]["decision_mode"] != "llm":
                    raise ValueError("invalid technical dropout")
            if a.kind == "idle":
                prepared.append((a, signature, None))
                continue
            if a.step != self.t or a.agent_id not in self.by_id:
                raise ValueError("action step/agent mismatch")
            valid_ob = self.observe(a.agent_id, a.step)
            valid_feed = {p["content_id"]: p for p in valid_ob.local_information["posts"]}
            feed = a.payload["observed_posts"]
            if self.cfg.get("feed_policy") in FULL_THREAD_POLICIES and feed != list(valid_feed.values()):
                raise ValueError("shared thread observation must include every visible post and comment")
            for p in feed:
                original = valid_feed.get(p["content_id"])
                if original is None or any(p.get(k) != v for k, v in original.items() if k != "comments"):
                    raise ValueError("observation contains invisible/altered content")
                if any(c not in original["comments"] for c in p["comments"]):
                    raise ValueError("observation contains invisible comment")
            retained = retained_memory(self.memory[a.agent_id], a.step, self.cfg)
            used_memory = [m for m in retained if m["tick"] in a.payload["used_memory_ticks"]]
            if (self.cfg.get("decision_condition_policy")=="all_conditions_v1"
                    and self.by_id[a.agent_id]["decision_mode"]=="llm" and used_memory != retained):
                raise ValueError("all conditions require the complete retained personal memory")
            policy = self.cfg.get("belief_measurement_policy", "legacy") if self.by_id[a.agent_id]["decision_mode"] == "llm" else "legacy"
            answer = normalize_answer(a.payload["answer"], feed, used_memory, self.reposted[a.agent_id], belief_policy=policy,
                                      comment_target_policy=self.cfg.get("comment_target", "first_displayed_post"))
            validate_belief_measurement(answer, required=self.by_id[a.agent_id]["decision_mode"] == "llm"
                and self.cfg.get("belief_measurement_policy") in ("subjective_credibility_v1", BINARY_SCORE_POLICY))
            if self.by_id[a.agent_id]["decision_mode"] == "llm":
                from decision_conditions import validate_condition_application
                validate_condition_application(answer, valid_ob)
            prepared.append((a, signature, answer))
        for a, signature, answer in prepared:
            aid = a.agent_id
            if a.payload.get("decision_status") == "technical_dropout":
                self.offline.setdefault(aid, {"tick": a.step, "reason": a.payload["failure_reason"]})
            if answer is not None:
                feed = a.payload["observed_posts"]
                before = self.beliefs[aid]
                credibility_before = self.credibility[aid]
                self.beliefs[aid] = answer["belief"]
                if "subjective_credibility" in answer:
                    self.credibility[aid] = answer["subjective_credibility"]
                    self.component_credibility[aid] = copy.deepcopy(answer["component_credibility"])
                if "condition_application" in answer:
                    self.condition_application[aid] = copy.deepcopy(answer["condition_application"])
                    self.condition_context_ref[aid] = answer["condition_context_ref"]
                self.last_updated[aid] = a.step
                for p in feed:
                    entry = self.exposure_history[aid].setdefault(p["content_id"], {
                        "root_content_id": p["root_content_id"], "author_id": p["author_id"],
                        "tick": a.step, "ticks": []})
                    if a.step not in entry["ticks"]:
                        entry["ticks"].append(a.step)
                    self.read_comments[aid].update(c["comment_id"] for c in p["comments"])
                if any(d.get("name") == "GT" and d.get("passed") for d in a.payload.get("draws", [])):
                    self.rule_corrected.add(aid)
                self.seen[aid].update(p["content_id"] for p in feed)
                if answer["comment"]["enabled"]:
                    cid = f"C{a.step:02d}-{aid}"
                    target = (answer["comment"]["target_content_id"] if self.cfg.get("comment_target") == "explicit_visible_root"
                              else feed[0]["content_id"])
                    self.comments[cid] = dict(comment_id=cid, author_id=aid, published_tick=a.step,
                        target_content_id=target, text=answer["comment"]["text"])
                if answer["repost"]["enabled"]:
                    target = self.posts[answer["repost"]["target_content_id"]]
                    cid = f"RP{a.step:02d}-{aid}"
                    self.posts[cid] = dict(content_id=cid, root_content_id=target["root_content_id"],
                        author_id=aid, original_author_id=target["original_author_id"],
                        published_tick=a.step, available_tick=a.step + 1, text=target["text"],
                        repost_text=answer["repost"]["text"], parent_content_id=target["content_id"])
                    self.reposted[aid].add(target["root_content_id"])
                remembered=(personal_memory_posts(feed) if self.cfg.get("memory_comment_policy")==MEMORY_POLICY else copy.deepcopy(feed))
                self.memory[aid].append(dict(agent_id=aid, tick=a.step, observed_posts=remembered,
                    belief_before=before, belief_after=answer["belief"],
                    subjective_credibility_before=credibility_before,
                    subjective_credibility_after=self.credibility[aid],
                    component_credibility=copy.deepcopy(self.component_credibility[aid]),
                    comment=answer["comment"], repost=answer["repost"]))
                self.memory[aid] = retained_memory(self.memory[aid], a.step+1, self.cfg)
                if aid in self.cohort and a.step >= self.government_tick and answer["belief"] == "reject":
                    self.transitions.setdefault(aid, a.step)
            self.applied[(a.step, aid)] = signature
        if self.t == self.government_tick - 1:
            self.cohort = {a for a, b in self.beliefs.items() if b == "believe"}

    def agent_state(self, aid):
        return dict(exposure_summary=exposure_summary(self.exposure_history[aid], [], self.t), current_belief=self.beliefs[aid], last_updated_tick=self.last_updated[aid],
                    decision_mode=self.by_id[aid]["decision_mode"], group=self.by_id[aid]["group"],
                    memory_count=len(self.memory[aid]), seen_count=len(self.seen[aid]),
                    subjective_credibility=self.credibility[aid],
                    component_credibility=copy.deepcopy(self.component_credibility[aid]),
                    condition_application=copy.deepcopy(self.condition_application[aid]),
                    condition_context_ref=self.condition_context_ref[aid],
                    synthetic_age=self.by_id[aid].get("synthetic_age"),
                    synthetic_region=self.by_id[aid].get("synthetic_region"),
                    synthetic_occupation=self.by_id[aid].get("synthetic_occupation"),
                    synthetic_mbti_type=self.by_id[aid].get("synthetic_mbti_type"),
                    reposted_roots=sorted(self.reposted[aid]))

    def snapshot(self):
        return dict(technical_offline=self.offline, exposure_history=self.exposure_history,
                    read_comments={a: sorted(v) for a,v in self.read_comments.items()},
                    rule_corrected=sorted(self.rule_corrected), tick=self.t, beliefs=self.beliefs, memory=self.memory,
                    subjective_credibility=self.credibility, component_credibility=self.component_credibility,
                    condition_application=self.condition_application, condition_context_ref=self.condition_context_ref,
                    posts=self.posts, comments=self.comments,
                    seen={a: sorted(x) for a, x in self.seen.items()},
                    reposted={a: sorted(x) for a, x in self.reposted.items()},
                    cohort=sorted(self.cohort), transitions=self.transitions)


def exposure_summary(history, feed, tick):
    events = copy.deepcopy(history)
    for p in feed:
        entry = events.setdefault(p["content_id"], {"root_content_id": p["root_content_id"],
            "author_id": p["author_id"], "tick": tick, "ticks": []})
        entry.setdefault("ticks", [entry["tick"]])
        if tick not in entry["ticks"]:
            entry["ticks"].append(tick)
    result = {}
    for e in events.values():
        root = e["root_content_id"]
        row = result.setdefault(root, {"post_count": 0, "presentations": 0, "authors": set(), "ticks": set()})
        row["post_count"] += 1
        row["authors"].add(e["author_id"])
        ticks = e.get("ticks", [e["tick"]])
        row["ticks"].update(ticks)
        row["presentations"] += len(ticks)
    return {root: {"observed_post_count": r["post_count"], "distinct_author_count": len(r["authors"]),
        "presentation_count": r["presentations"], "exposure_tick_count": len(r["ticks"]), "first_seen_tick": min(r["ticks"]),
        "last_seen_tick": max(r["ticks"])} for root, r in sorted(result.items())}


def allowed_evidence_ids(feed, memories):
    ids = set()
    for p in feed + [p for m in memories for p in m["observed_posts"]]:
        ids.add(p["content_id"])
        ids.update(c["comment_id"] for c in p.get("comments", []))
        # Provider text holds original/root text, not the repost caption.
        if isinstance(p.get("text"), str) and p["text"].strip() and p.get("root_content_id"):
            ids.add(p["root_content_id"])
        # Complete-thread observations also display followed accounts' relay
        # captions. Those visible transport IDs are valid evidence, not new roots.
        ids.update(r["content_id"] for r in p.get("relay_context", []))
    return ids


def normalize_answer(raw, feed, memories, already_reposted, belief_policy="legacy", comment_target_policy="first_displayed_post"):
    if not feed:
        raise ValueError("no content must use idle")
    answer = copy.deepcopy(raw)
    if belief_policy == BINARY_SCORE_POLICY:
        validate_belief_measurement(answer, required=True)
        answer["belief"] = score_to_belief(answer["subjective_credibility"])
        answer["belief_basis"] = "subjective_credibility > 50; score=50 is reject"
    repairs = list(answer.get("format_repairs", []))
    # Only the explicit false shorthand is unambiguous. Never infer a true action.
    if answer.get("repost") is False and answer.get("target_content_id") is None and answer.get("text", "") == "":
        answer["repost"] = {"enabled": False, "target_content_id": None, "text": ""}
        answer.pop("target_content_id", None)
        answer.pop("text", None)
        repairs.append("explicit_false_repost_to_disabled_object")
    if repairs:
        answer["format_repairs"] = repairs
    if answer.get("belief") not in ("believe", "uncertain", "reject", "unjudged"):
        raise ValueError("invalid belief")
    validate_belief_measurement(answer)
    for field in ("comment", "repost"):
        item = answer.get(field)
        if not isinstance(item, dict) or type(item.get("enabled")) is not bool or not isinstance(item.get("text"), str):
            raise ValueError("invalid action schema")
        if item["enabled"] and field == "comment" and not item["text"].strip():
            raise ValueError("empty enabled comment")
    if comment_target_policy == "explicit_visible_root":
        comment_target=answer["comment"].get("target_content_id")
        if answer["comment"]["enabled"] and (not isinstance(comment_target,str) or comment_target not in {p["content_id"] for p in feed}):
            raise ValueError("invalid/invisible comment target")
        if not answer["comment"]["enabled"]:
            answer["comment"]["target_content_id"] = None
    visible_ids = allowed_evidence_ids(feed, memories)
    evidence = answer.get("evidence_ids")
    if not isinstance(evidence, list) or any(not isinstance(i, str) or i not in visible_ids for i in evidence):
        raise ValueError("invalid/invisible evidence")
    answer["decision_status"] = "applied"
    if answer["repost"]["enabled"]:
        target = next((p for p in feed if p["content_id"] == answer["repost"].get("target_content_id")), None)
        if target is None:
            raise ValueError("invisible repost target")
        if target["root_content_id"] in already_reposted:
            answer["repost"] = {"enabled": False, "target_content_id": None, "text": ""}
            answer["decision_status"] = "partially_applied"
            answer["repost_rejection_reason"] = "duplicate_root_repost"
    for field in ("comment", "repost"):
        if not answer[field]["enabled"]:
            answer[field]["text"] = ""
    if not answer["repost"]["enabled"]:
        answer["repost"]["target_content_id"] = None
    return answer


COMPONENT_KEYS = ("funds_redirected", "safety_delayed", "causal_link")
BINARY_SCORE_POLICY = "binary_score_gt50_v1"


def score_to_belief(score):
    """One authoritative boundary: >50 believe; <=50 reject. No rounding."""
    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 100:
        raise ValueError("invalid belief measurement")
    return "believe" if score > 50 else "reject"


def belief_states(policy):
    return ("unjudged", "believe", "reject") if policy == BINARY_SCORE_POLICY else ("unjudged", "believe", "uncertain", "reject")


def validate_belief_measurement(answer, required=False):
    """Validate the four self-report scores. Classification is a separate policy."""
    present = any(k in answer for k in ("subjective_credibility", "component_credibility"))
    if not present and not required:
        return
    def score(value):
        return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100
    components = answer.get("component_credibility")
    if (not score(answer.get("subjective_credibility")) or not isinstance(components, dict)
            or set(components) != set(COMPONENT_KEYS) or not all(score(v) for v in components.values())):
        raise ValueError("invalid belief measurement")


def empty_answer(belief):
    return dict(belief=belief, comment={"enabled": False, "text": ""},
                repost={"enabled": False, "target_content_id": None, "text": ""}, evidence_ids=[])


@register("decision", "rumor_v6.decision")
class V4Decision(DecisionModel):
    def __init__(self, config, prompt_file, audit_dir, llm_kind="scripted"):
        self.cfg = config
        self.mode = llm_kind
        if llm_kind not in ("scripted", "openai"):
            raise ValueError("unsupported llm_kind")
        self.template = Path(prompt_file).read_text(encoding="utf-8").split("```text", 1)[1].split("```", 1)[0].strip()
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.client = None
        if llm_kind == "openai":
            from llm_client import LiveClient
            self.client = LiveClient(config, self.audit_dir)

    def _rule(self, ob):
        feed = ob.local_information["posts"]
        state = ob.local_physical["current_belief"]
        answer = empty_answer(state)
        draws = []
        # Per-agent/tick stream: calls, retries and ordering cannot shift rule draws.
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(
            [self.cfg["behavior_seed"], ob.step, int(ob.agent_id[1:])])) )
        def trial(name, probability):
            value = float(rng.random())
            draws.append(dict(name=name, probability=probability, uniform=value, passed=value < probability))
            return value < probability
        corrections = [p for p in feed if p["root_content_id"] == "G001"]
        pool = corrections or [p for p in feed if p["root_content_id"] == "P001"]
        if not pool:
            return answer, draws
        target = pool[0]
        answer["evidence_ids"] = [target["content_id"]]
        eligible = target["root_content_id"] not in ob.local_physical["already_reposted"]
        if corrections:
            gt = ob.local_physical.get("government_trust")
            if trial("GT", self.cfg["gt"] if gt is None else gt):
                answer["belief"] = "reject"
                repost = eligible and trial("RF", self.cfg["rf"])
            else:
                repost = False  # GT failure preserves even unjudged.
        else:
            inside = ob.local_physical["persona"]["group"] == "inside"
            pb, rc = {0.0: (.579, .579, .100, .100), .2: (.679, .479, .117, .083),
                      .4: (.779, .379, .135, .065)}[self.cfg["pbd"]][0 if inside else 1::2]
            if self.cfg.get("rule_source_trust_mode") == "individual_pb":
                pb = ob.local_physical.get("source_trust")
                if pb is None:
                    raise ValueError("individual_pb requires a frozen source_trust assignment")
            if state in ("unjudged", "uncertain") or (state == "reject" and self.cfg.get("rule_reconsider_rumor", False) and not ob.local_physical.get("rule_corrected", False)):
                answer["belief"] = "believe" if trial("PB", pb) else "reject"
            repost = answer["belief"] == "believe" and eligible and trial("RC", rc)
        if repost:
            answer["repost"] = {"enabled": True, "target_content_id": target["content_id"], "text": ""}
        return answer, draws

    def _scripted(self, ob):
        # Fixed artificial replies exercise propagation, comments and duplicate rejection.
        feed = ob.local_information["posts"]
        target = next((p for p in feed if p["root_content_id"] == "G001"), feed[0])
        answer = empty_answer("reject" if target["root_content_id"] == "G001" else "believe")
        answer["repost"] = {"enabled": True, "target_content_id": target["content_id"], "text": "离线工程测试附言"}
        answer["comment"] = {"enabled": True, "text": "离线工程测试评论"}
        if ob.local_physical.get("comment_target_policy") == "explicit_visible_root":
            answer["comment"]["target_content_id"] = target["content_id"]
        answer["evidence_ids"] = [target["content_id"]]
        if ob.local_physical.get("belief_measurement_policy") in ("subjective_credibility_v1", BINARY_SCORE_POLICY):
            value = 10 if answer["belief"] == "reject" else 90
            answer["subjective_credibility"] = value
            answer["component_credibility"] = {k:value for k in COMPONENT_KEYS}
        if ob.local_physical.get("belief_measurement_policy") == BINARY_SCORE_POLICY:
            answer.pop("belief") # exercise the same score-only schema as the live prompt
        if ob.local_physical.get("decision_condition_policy") == "all_conditions_v1":
            from decision_conditions import scripted_condition_application
            answer.update(scripted_condition_application(ob))
        return answer

    def decide_batch(self, obs, memories):
        from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
        observations = copy.deepcopy(list(obs))
        if len({o.agent_id for o in observations}) != len(observations):
            raise ValueError("duplicate agent in observation batch")
        if self.mode=='openai' and self.cfg.get('prompt_encoding')=='lossless_thread_refs_v1':
            self.client.preflight_batch(observations,self.template)
        workers = int(self.cfg.get("max_concurrency", 1))
        if workers == 1 or self.mode != "openai":
            return self._decide_serial(observations, memories)
        results = {}
        errors = []
        next_index = 0
        # Keep a bounded rolling window; observations remain frozen for the tick.
        # On any global error stop refilling, drain in-flight work, then raise.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending = {}
            def submit_one(index):
                future = pool.submit(self._decide_serial, [observations[index]], memories)
                pending[future] = index
            while next_index < min(workers, len(observations)):
                submit_one(next_index)
                next_index += 1
            try:
                while pending:
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        index = pending.pop(future)
                        try:
                            results[index] = future.result()
                        except Exception as exc:
                            errors.append(exc)
                    if not errors:
                        while len(pending) < workers and next_index < len(observations):
                            submit_one(next_index)
                            next_index += 1
            except KeyboardInterrupt:
                self.client.gate.halt()
                for future in pending:
                    future.cancel()
                print("\n正在暂停：停止新请求，等待已发送的请求收尾并保存缓存。请勿直接关闭窗口。", flush=True)
                raise
            if errors:
                from llm_client import QuotaPause
                raise next((e for e in errors if isinstance(e, QuotaPause)), errors[0])
        return [action for i in range(len(observations)) for action in results[i]]

    def _decide_serial(self, obs, memories):
        actions = []
        # Sequential requests intentionally stay below V4's maximum concurrency of five.
        for ob in obs:
            feed = ob.local_information["posts"]
            if not feed:
                actions.append(Action(agent_id=ob.agent_id, step=ob.step, kind="idle", source="rule",
                                      payload={"decision_status": "idle", "dry_run": self.mode == "scripted"}))
                continue
            used = copy.deepcopy(feed)
            draws, meta = [], {}
            is_llm = ob.local_physical["persona"]["decision_mode"] == "llm"
            try:
                if not is_llm:
                    raw, draws = self._rule(ob)
                elif self.mode == "scripted":
                    raw = self._scripted(ob)
                else:
                    raw, used, meta = self.client.decide(ob, self.template)
                    if ob.local_physical.get("belief_measurement_policy") != BINARY_SCORE_POLICY and raw.get("belief") not in ("believe", "uncertain", "reject"):
                        raise ValueError("LLM must not return unjudged")
                validate_belief_measurement(raw, required=is_llm and
                    ob.local_physical.get("belief_measurement_policy") in ("subjective_credibility_v1", BINARY_SCORE_POLICY))
                if is_llm:
                    from decision_conditions import validate_condition_application
                    validate_condition_application(raw, ob)
                used_ticks = meta.get("used_memory_ticks", [m["tick"] for m in ob.local_physical["memory"]])
                used_memory = [m for m in ob.local_physical["memory"] if m["tick"] in used_ticks]
                policy = ob.local_physical.get("belief_measurement_policy", "legacy") if is_llm else "legacy"
                answer = normalize_answer(raw, used, used_memory, ob.local_physical["already_reposted"], belief_policy=policy,
                                          comment_target_policy=ob.local_physical.get("comment_target_policy", "first_displayed_post"))
            except Exception as exc:
                from llm_client import AgentRequestFailure, FormatAttemptsExhausted
                if is_llm and isinstance(exc, (AgentRequestFailure, FormatAttemptsExhausted)):
                    payload = {"decision_status": "technical_dropout", "failure_reason": type(exc).__name__,
                               "dry_run": False}
                    dump(self.audit_dir / f"dropout-{ob.step:02d}-{ob.agent_id}.json", {
                        "agent_id": ob.agent_id, "tick": ob.step, **payload,
                        "note": "proposed dropout; effective only after complete tick commit"})
                    actions.append(Action(agent_id=ob.agent_id, step=ob.step, kind="idle", source="rule", payload=payload))
                    continue
                dump(self.audit_dir / f"failure-{ob.step:02d}-{ob.agent_id}.json", {
                    "agent_id": ob.agent_id, "tick": ob.step, "decision_status": "error",
                    "error_type": type(exc).__name__, "file_error": {"filename":getattr(exc,"filename",None), "filename2":getattr(exc,"filename2",None), "errno":getattr(exc,"errno",None), "winerror":getattr(exc,"winerror",None)}, "observed_posts": used,
                    "note": "batch not committed; see safe request diagnostics; no fallback"})
                raise
            payload = dict(answer=answer, raw_answer=raw, observed_posts=used, draws=draws,
                           dry_run=self.mode == "scripted", api=meta, used_memory_ticks=used_ticks,
                           decision_status=answer["decision_status"])
            actions.append(Action(agent_id=ob.agent_id, step=ob.step, kind="decide", payload=payload,
                                  source="llm" if is_llm and self.mode == "openai" else "rule"))
        return actions


@register("collector", "rumor_v6.metrics")
class V4Metrics(MetricCollector):
    def collect(self, env, actions, t):
        result = {}
        labels = belief_states(env.cfg.get("belief_measurement_policy", "legacy"))
        if any(b not in labels for b in env.beliefs.values()):
            raise ValueError("belief state incompatible with active measurement policy")
        for mode in ("all", "llm", "rule"):
            counts = Counter(b for a, b in env.beliefs.items() if mode == "all" or env.by_id[a]["decision_mode"] == mode)
            for b in labels:
                result[f"{mode}_{b}"] = counts[b]
            judged = counts["believe"] + counts["reject"]
            result[f"{mode}_judged_n"] = judged
            result[f"{mode}_believe_rate_judged"] = counts["believe"] / judged if judged else None
        result.update(remaining_agents=len(env.by_id)-len(env.offline), technical_dropout_count=len(env.offline),
            remaining_llm=sum(r["decision_mode"] == "llm" and aid not in env.offline for aid,r in env.by_id.items()),
            remaining_rule=sum(r["decision_mode"] == "rule" and aid not in env.offline for aid,r in env.by_id.items()))
        for belief in labels:
            result["remaining_"+belief] = sum(b == belief and aid not in env.offline for aid,b in env.beliefs.items())
        for root, prefix in (("P001", "rumor"), ("G001", "official")):
            first_ticks = [min(tick for h in history.values() if h["root_content_id"] == root
                               for tick in h.get("ticks", [h["tick"]]))
                           for history in env.exposure_history.values()
                           if any(h["root_content_id"] == root for h in history.values())]
            result[prefix+"_readers_this_tick"] = sum(any(p["root_content_id"] == root
                for p in a.payload.get("observed_posts", [])) for a in actions)
            result[prefix+"_new_reach"] = sum(tick == t for tick in first_ticks)
            result[prefix+"_cumulative_reach"] = len(first_ticks)
            result[prefix+"_coverage_rate"] = len(first_ticks)/len(env.by_id)
        scores = [v for aid,v in env.credibility.items() if env.by_id[aid]["decision_mode"] == "llm" and v is not None]
        result["llm_credibility_reported_n"] = len(scores)
        result["llm_credibility_mean"] = mean(scores) if scores else None
        result.update(posts=len(env.posts), comments=len(env.comments),
            reread_presentations=sum(p.get("is_reread", False) for a in actions for p in a.payload.get("observed_posts", [])),
            visible_comment_presentations=sum(len(p.get("comments", [])) for a in actions for p in a.payload.get("observed_posts", [])),
            partial_actions=sum(a.payload.get("decision_status") == "partially_applied" for a in actions),
            idle_actions=sum(a.kind == "idle" for a in actions),
            tbu_cohort=len(env.cohort), tbu_completed=len(env.transitions),
            tbu_engineering=mean(v - env.government_tick for v in env.transitions.values()) if env.transitions else None)
        return result

    def columns(self):
        return []
