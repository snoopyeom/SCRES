import argparse
import csv
import logging
import time
import random
from typing import List, Tuple, Dict, Any

from aas_pathfinder import (
    load_machines_from_mongo,
    build_graph_from_aas,
    haversine,
    Machine,
)
from graph import Graph
from a_star import AStar

logger = logging.getLogger(__name__)

def select_machines(machines: Dict[str, Machine]) -> List[Machine]:
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

def ga_shortest_path_process_based(
    machines: Dict[str, Any],
    process_flow: List[str],
    graph: Graph,
    generations: int = 50,
    pop_size: int = 30,
    mutation_rate: float = 0.1,
) -> Tuple[List[str], float, int, float]:

    by_process: Dict[str, List[str]] = {}
    for m in machines.values():
        by_process.setdefault(m.process, []).append(m.name)

    def random_individual() -> List[int]:
        return [random.randint(0, len(by_process[proc]) - 1) for proc in process_flow]

    def decode_individual(ind: List[int]) -> List[str]:
        return [by_process[proc][idx] for proc, idx in zip(process_flow, ind)]

    def fitness(ind: List[int]) -> float:
        path = decode_individual(ind)
        return path_distance(graph, path)

    def crossover(p1: List[int], p2: List[int]) -> List[int]:
        point = random.randint(1, len(p1) - 1)
        return p1[:point] + p2[point:]

    def mutate(ind: List[int]) -> None:
        i = random.randint(0, len(ind) - 1)
        proc = process_flow[i]
        current = ind[i]
        choices = list(range(len(by_process[proc])))
        if len(choices) <= 1:
            return  # 후보가 1개뿐이면 돌연변이 불가능
        choices.remove(current)
        ind[i] = random.choice(choices)


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
    best_path = decode_individual(best)
    t1 = time.perf_counter()
    return best_path, fitness(best), generations, t1 - t0

def main() -> None:
    parser = argparse.ArgumentParser(description="Compare path finding algorithms")
    parser.add_argument("--aas-dir", default="C:/Users/JeongHoon/SCRES/aas_instances", help="Directory with AAS JSON files")
    parser.add_argument("--algorithm", choices=["all", "astar", "dijkstra", "ga"], default="all")
    parser.add_argument("--generations", type=int, default=50, help="GA generations")
    parser.add_argument("--population", type=int, default=30, help="GA population size")
    parser.add_argument("--mutation", type=float, default=0.1, help="GA mutation rate")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    machines = load_machines_from_mongo(
        mongo_uri="mongodb://localhost:27017",
        db_name="test_db",
        collection_name="aas_documents"
    )
    if not machines:
        logger.info("No machines loaded")
        return

    selected = select_machines(machines)
    if len(selected) < 2:
        logger.info("Not enough machines for path finding")
        return

    # machines 전체에서 좌표를 수집하여 graph 구성
    coords = {m.name: m.coords for m in machines.values()}

    graph = build_graph_from_aas(coords)
    node_names = [m.name for m in selected]
    results = []

    # A*
    a_path, a_cost, a_steps, a_time = sequential_search(graph, node_names, run_astar)
    results.append(["astar", a_path, a_cost, a_time, True, a_steps])

    # Dijkstra
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

    # GA (공정 기반)
    if args.algorithm in ("all", "ga"):
        process_flow = ["Forging", "Turning", "Milling", "Grinding"]
        g_path, g_cost, g_iters, g_time = ga_shortest_path_process_based(
            machines=machines,
            process_flow=process_flow,
            graph=graph,
            generations=args.generations,
            pop_size=args.population,
            mutation_rate=args.mutation
        )
        results.append([
            "ga",
            g_path,
            g_cost,
            g_time,
            abs(g_cost - a_cost) < 1e-6,
            g_iters,
        ])

    with open("results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["algorithm", "path", "distance_km", "time_s", "optimal", "iterations"])
        for r in results:
            writer.writerow(r)

    header = ["algorithm", "path", "distance_km", "time_s", "optimal", "iterations"]
    print("\t".join(header))
    for alg, path, dist, tm, opt, iters in results:
        time_str = f"{tm:.2E}" if tm else "0"
        print(f"{alg}\t{path}\t{dist}\t{time_str}\t{str(opt).upper()}\t{iters}")

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

def sequential_search(
    graph: Graph,
    nodes: List[str],
    algo_func,
) -> Tuple[List[str], float, int, float]:
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

if __name__ == "__main__":
    main()
    