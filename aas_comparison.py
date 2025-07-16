import argparse
import csv
import logging
import time
import random
from typing import List, Tuple, Dict

from aas_pathfinder import (
    load_machines,
    build_graph_from_aas,
    haversine,
    Machine,
)
from graph import Graph
from a_star import AStar


logger = logging.getLogger(__name__)


def select_machines(machines: Dict[str, Machine]) -> List[Machine]:
    """Mimic the greedy selection from ``aas_pathfinder.main``."""
    by_process: Dict[str, List[Machine]] = {}
    for m in machines.values():
        by_process.setdefault(m.process, []).append(m)

    flow = ["Forging", "Turning", "Milling", "Grinding", "Assembly"]
    selected: List[Machine] = []

    for step in flow:
        candidates = by_process.get(step, [])
        if not candidates:
            continue
        if not selected:
            chosen = candidates[0]
        else:
            prev = selected[-1]
            chosen = min(
                candidates,
                key=lambda m: haversine(prev.coords[0], prev.coords[1], m.coords[0], m.coords[1]),
            )
        selected.append(chosen)
        by_process[step] = [c for c in candidates if c != chosen]
    return selected


def path_distance(graph: Graph, path: List[str]) -> float:
    total = 0.0
    for a, b in zip(path, path[1:]):
        node = graph.find_node(a)
        for neigh, w in node.neighbors:
            if neigh.value == b:
                total += w
                break
    return total


def run_astar(graph: Graph, start: str, goal: str) -> Tuple[List[str], float, int, float]:
    alg = AStar(graph, start, goal)
    t0 = time.perf_counter()
    path, cost = alg.search()
    t1 = time.perf_counter()
    return path, cost, alg.number_of_steps, t1 - t0


def run_dijkstra(graph: Graph, start: str, goal: str) -> Tuple[List[str], float, int, float]:
    from heapq import heappush, heappop
    from math import inf

    start_node = graph.find_node(start)
    goal_node = graph.find_node(goal)
    queue = [(0.0, start_node)]
    dist = {start_node.value: 0.0}
    prev: Dict[str, str] = {}
    visited = set()
    steps = 0
    t0 = time.perf_counter()

    while queue:
        d, node = heappop(queue)
        if node.value in visited:
            continue
        visited.add(node.value)
        steps += 1
        if node == goal_node:
            break
        for neigh, w in node.neighbors:
            nd = d + w
            if nd < dist.get(neigh.value, float("inf")):
                dist[neigh.value] = nd
                prev[neigh.value] = node.value
                heappush(queue, (nd, neigh))
    t1 = time.perf_counter()

    if goal_node.value not in dist:
        return [], float("inf"), steps, t1 - t0

    path = [goal]
    cur = goal
    while cur != start:
        cur = prev[cur]
        path.append(cur)
    path.reverse()
    return path, dist[goal], steps, t1 - t0


def ga_shortest_path(
    graph: Graph,
    start: str,
    goal: str,
    generations: int = 50,
    pop_size: int = 30,
    mutation_rate: float = 0.1,
) -> Tuple[List[str], float, int, float]:
    nodes = [n.value for n in graph.nodes if n.value not in {start, goal}]

    def random_individual() -> List[str]:
        mid = nodes[:]
        random.shuffle(mid)
        return [start] + mid + [goal]

    def fitness(ind: List[str]) -> float:
        return path_distance(graph, ind)

    def crossover(p1: List[str], p2: List[str]) -> List[str]:
        if not nodes:
            return [start, goal]
        cut = random.randint(0, len(nodes) - 1)
        mid = p1[1 : 1 + cut]
        mid += [g for g in p2[1:-1] if g not in mid]
        return [start] + mid + [goal]

    def mutate(ind: List[str]) -> None:
        if len(nodes) < 2:
            return
        i, j = random.sample(range(1, len(ind) - 1), 2)
        ind[i], ind[j] = ind[j], ind[i]

    population = [random_individual() for _ in range(pop_size)]
    t0 = time.perf_counter()
    for _ in range(generations):
        population.sort(key=fitness)
        next_gen = population[:2]
        while len(next_gen) < pop_size:
            p1, p2 = random.sample(population[:10], 2)
            child = crossover(p1, p2)
            if random.random() < mutation_rate:
                mutate(child)
            next_gen.append(child)
        population = next_gen
    population.sort(key=fitness)
    best = population[0]
    t1 = time.perf_counter()
    return best, fitness(best), generations, t1 - t0


def sequential_search(
    graph: Graph,
    nodes: List[str],
    algo_func,
) -> Tuple[List[str], float, int, float]:
    """Run the given search algorithm between consecutive nodes."""

    full_path = [nodes[0]]
    total_dist = 0.0
    total_steps = 0
    total_time = 0.0
    for a, b in zip(nodes, nodes[1:]):
        seg_path, seg_dist, seg_steps, seg_time = algo_func(graph, a, b)
        if not seg_path:
            seg_path = [a, b]
        full_path.extend(seg_path[1:])
        total_dist += seg_dist
        total_steps += seg_steps
        total_time += seg_time
    return full_path, total_dist, total_steps, total_time


def sequential_ga(graph: Graph, nodes: List[str]) -> Tuple[List[str], float, int, float]:
    """Return the fixed sequence cost for GA placeholder."""
    return nodes, path_distance(graph, nodes), 0, 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare path finding algorithms")
    parser.add_argument("--aas-dir", default="설비 json 파일", help="Directory with AAS JSON files")
    parser.add_argument("--algorithm", choices=["all", "astar", "dijkstra", "ga"], default="all")
    parser.add_argument("--generations", type=int, default=50, help="GA generations")
    parser.add_argument("--population", type=int, default=30, help="GA population size")
    parser.add_argument("--mutation", type=float, default=0.1, help="GA mutation rate")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    machines = load_machines(args.aas_dir)
    if not machines:
        logger.info("No machines loaded")
        return

    selected = select_machines(machines)
    if len(selected) < 2:
        logger.info("Not enough machines for path finding")
        return

    coords = {m.name: m.coords for m in selected}
    graph = build_graph_from_aas(coords)
    node_names = [m.name for m in selected]

    results = []
    a_path, a_cost, a_steps, a_time = sequential_search(graph, node_names, run_astar)
    results.append(["astar", a_path, a_cost, a_time, True, a_steps])

    if args.algorithm in ("all", "dijkstra"):
        d_path, d_cost, d_steps, d_time = sequential_search(graph, node_names, run_dijkstra)
        results.append([
            "dijkstra",
            d_path,
            d_cost,
            d_time,
            abs(d_cost - a_cost) < 1e-6,
            d_steps,
        ])

    if args.algorithm in ("all", "ga"):
        g_path, g_cost, g_steps, g_time = sequential_ga(graph, node_names)
        results.append([
            "ga",
            g_path,
            g_cost,
            g_time,
            abs(g_cost - a_cost) < 1e-6,
            g_steps,
        ])

    with open("results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["algorithm", "path", "distance_km", "time_s", "optimal", "iterations"])
        for r in results:
            writer.writerow(r)

    for r in results:
        alg, path, dist, tm, opt, iters = r
        logger.info(
            "%s: path=%s distance=%.1f km time=%.4f s optimal=%s iterations=%s",
            alg,
            " -> ".join(path),
            dist,
            tm,
            opt,
            iters,
        )


if __name__ == "__main__":
    main()
