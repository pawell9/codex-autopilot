import json
import unittest
from collections import defaultdict, deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL = json.loads((ROOT / "design" / "lifecycle-model.json").read_text())


def reachable(transitions, start, target):
    graph = defaultdict(set)
    for edge in transitions:
        if "*" not in edge["from"] and "*" not in edge["to"]:
            graph[edge["from"]].add(edge["to"])
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node == target:
            return True
        for successor in graph[node] - seen:
            seen.add(successor)
            queue.append(successor)
    return False


class StateMachineModelTests(unittest.TestCase):
    def test_success_terminal_is_reachable(self):
        self.assertTrue(reachable(MODEL["run_transitions"], MODEL["initial"], MODEL["success_terminal"]))

    def test_every_required_success_edge_is_necessary(self):
        transitions = MODEL["run_transitions"]
        for edge_id in MODEL["required_success_edges"]:
            mutated = [edge for edge in transitions if edge["id"] != edge_id]
            with self.subTest(removed=edge_id):
                self.assertFalse(reachable(mutated, MODEL["initial"], MODEL["success_terminal"]))

    def test_local_machines_have_no_nonterminal_dead_ends(self):
        for name, machine in MODEL["machines"].items():
            states = {machine["initial"], *machine["terminal"]}
            outgoing = defaultdict(set)
            for source, target in machine["transitions"]:
                states.update((source, target))
                outgoing[source].add(target)
            for state in states - set(machine["terminal"]):
                with self.subTest(machine=name, state=state):
                    self.assertTrue(outgoing[state], f"{name}:{state} is a dead end")

    def test_local_success_and_safe_terminal_states_are_reachable(self):
        for name, machine in MODEL["machines"].items():
            graph = defaultdict(set)
            for source, target in machine["transitions"]:
                graph[source].add(target)
            seen = {machine["initial"]}
            queue = deque(seen)
            while queue:
                node = queue.popleft()
                for successor in graph[node] - seen:
                    seen.add(successor)
                    queue.append(successor)
            with self.subTest(machine=name):
                self.assertTrue(set(machine["terminal"]) <= seen)


if __name__ == "__main__":
    unittest.main()
