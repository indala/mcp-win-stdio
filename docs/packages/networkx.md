# `networkx` (>=3.2.1 (`>=3.0` in `rag` & `requirements.txt`))

> Link-graph trees in RAG and directed multigraph (`MultiDiGraph`) architecture modeling/tracing in Arch.

## Package Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Third-Party Runtime |
| **Version Constraint** | `>=3.2.1 (`>=3.0` in `rag` & `requirements.txt`)` |
| **Declared / Referenced In** | `requirements.txt`, `packages/mcp-win-stdio-rag/pyproject.toml`, `packages/mcp-win-stdio-arch/pyproject.toml` |
| **Repo Imports (2)** | `networkx (packages/mcp-win-stdio-arch/src/mcp_win_stdio/arch/graph.py)`; `networkx (packages/mcp-win-stdio-rag/src/mcp_win_stdio/rag/crawler.py)` |

## Symbols Used Directly in `mcp-win-stdio`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `networkx.DiGraph` | `class` · Init: `(*args, backend=None, **kwargs)` · Key attrs: `add_edge`, `add_edges_from`, `add_node`, `add_nodes_from`, `add_weighted_edges_from`, `adj`, `adjacency`, `adjlist_inner_dict_factory`<br>Base class for directed graphs.<br>**Used in:** `packages/mcp-win-stdio-rag/src/mcp_win_stdio/rag/crawler.py` |
| `networkx.MultiDiGraph` | `class` · Init: `(*args, backend=None, **kwargs)` · Key attrs: `add_edge`, `add_edges_from`, `add_node`, `add_nodes_from`, `add_weighted_edges_from`, `adj`, `adjacency`, `adjlist_inner_dict_factory`<br>A directed graph class that can store multiedges.<br>**Used in:** `packages/mcp-win-stdio-arch/src/mcp_win_stdio/arch/graph.py` |
| `networkx.node_link_data` | Imported/accessed symbol in `mcp-win-stdio`.<br>**Used in:** `packages/mcp-win-stdio-rag/src/mcp_win_stdio/rag/crawler.py` |

## Public Functions, Classes & Variables

### `networkx`

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| **`class AmbiguousSolution`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Raised if more than one valid solution exists for an intermediary step of an algorithm. |
| **`class ArborescenceIterator`** | `class` · Init: `(G, weight='weight', minimum=True, init_partition=None)` · Attrs: `Partition` · Methods: `Partition(mst_weight: float, partition_dict: dict) -> None`<br>Iterate over all spanning arborescences of a graph in either increasing or decreasing cost. |
| **`class DiGraph`** | `class` · Init: `(*args, backend=None, **kwargs)` · Attrs: `add_edge`, `add_edges_from`, `add_node`, `add_nodes_from`, `add_weighted_edges_from`, `adj`, `adjacency`, `adjlist_inner_dict_factory`, `adjlist_outer_dict_factory`, `clear` · Methods: `add_edge(self, u_of_edge, v_of_edge, **attr)`, `add_edges_from(self, ebunch_to_add, **attr)`, `add_node(self, node_for_adding, **attr)`, `add_nodes_from(self, nodes_for_adding, **attr)`, `add_weighted_edges_from(self, ebunch_to_add, weight='weight', **attr)`, `adjacency(self)`<br>Base class for directed graphs. |
| **`class EdgePartition`** | `class` · Init: `(*values)` · Attrs: `EXCLUDED`, `INCLUDED`, `OPEN`<br>An enum to store the state of an edge partition. The enum is written to the edges of a graph before being pasted to `kruskal_mst_edges`. Options are: |
| **`class ExceededMaxIterations`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Raised if a loop iterates too many times without breaking. |
| **`class Graph`** | `class` · Init: `(*args, backend=None, **kwargs)` · Attrs: `add_edge`, `add_edges_from`, `add_node`, `add_nodes_from`, `add_weighted_edges_from`, `adj`, `adjacency`, `adjlist_inner_dict_factory`, `adjlist_outer_dict_factory`, `clear` · Methods: `add_edge(self, u_of_edge, v_of_edge, **attr)`, `add_edges_from(self, ebunch_to_add, **attr)`, `add_node(self, node_for_adding, **attr)`, `add_nodes_from(self, nodes_for_adding, **attr)`, `add_weighted_edges_from(self, ebunch_to_add, weight='weight', **attr)`, `adjacency(self)`<br>Base class for undirected graphs. |
| **`class GraphMLReader`** | `class` · Init: `(node_type=<class 'str'>, edge_key_type=<class 'int'>, force_multigraph=False)` · Attrs: `NS_GRAPHML`, `NS_XSI`, `NS_Y`, `SCHEMALOCATION`, `add_edge`, `add_node`, `construct_types`, `convert_bool`, `decode_data_elements`, `find_graphml_keys` · Methods: `add_edge(self, G, edge_element, graphml_keys)`, `add_node(self, G, node_xml, graphml_keys, defaults)`, `construct_types(self)`, `decode_data_elements(self, graphml_keys, obj_xml)`, `find_graphml_keys(self, graph_element)`, `get_xml_type(self, key)`<br>Read a GraphML document. Produces NetworkX graph objects. |
| **`class GraphMLWriter`** | `class` · Init: `(graph=None, encoding='utf-8', prettyprint=True, infer_numeric_types=False, named_key_ids=False, edge_id_from_attribute=None)` · Attrs: `NS_GRAPHML`, `NS_XSI`, `NS_Y`, `SCHEMALOCATION`, `add_attributes`, `add_data`, `add_edges`, `add_graph_element`, `add_graphs`, `add_nodes` · Methods: `add_attributes(self, scope, xml_obj, data, default)`, `add_data(self, name, element_type, value, scope='all', default=None)`, `add_edges(self, G, graph_element)`, `add_graph_element(self, G)`, `add_graphs(self, graph_list)`, `add_nodes(self, G, graph_element)`<br>Public class. |
| **`class HasACycle`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Raised if a graph has a cycle when an algorithm expects that it will have no cycles. |
| `LCF_graph()` | `function` · Signature: `(n, shift_list, repeats, create_using=None, *, backend=None, **backend_kwargs)`<br>Return the cubic graph specified in LCF notation. |
| `LFR_benchmark_graph()` | `function` · Signature: `(n, tau1, tau2, mu, average_degree=None, min_degree=None, max_degree=None, min_community=None, max_community=None, tol=1e-07, max_iters=500, seed=None, *, backend=None, **backend_kwargs)`<br>Returns the LFR benchmark graph. |
| **`class MultiDiGraph`** | `class` · Init: `(*args, backend=None, **kwargs)` · Attrs: `add_edge`, `add_edges_from`, `add_node`, `add_nodes_from`, `add_weighted_edges_from`, `adj`, `adjacency`, `adjlist_inner_dict_factory`, `adjlist_outer_dict_factory`, `clear` · Methods: `add_edge(self, u_for_edge, v_for_edge, key=None, **attr)`, `add_edges_from(self, ebunch_to_add, **attr)`, `add_node(self, node_for_adding, **attr)`, `add_nodes_from(self, nodes_for_adding, **attr)`, `add_weighted_edges_from(self, ebunch_to_add, weight='weight', **attr)`, `adjacency(self)`<br>A directed graph class that can store multiedges. |
| **`class MultiGraph`** | `class` · Init: `(*args, backend=None, **kwargs)` · Attrs: `add_edge`, `add_edges_from`, `add_node`, `add_nodes_from`, `add_weighted_edges_from`, `adj`, `adjacency`, `adjlist_inner_dict_factory`, `adjlist_outer_dict_factory`, `clear` · Methods: `add_edge(self, u_for_edge, v_for_edge, key=None, **attr)`, `add_edges_from(self, ebunch_to_add, **attr)`, `add_node(self, node_for_adding, **attr)`, `add_nodes_from(self, nodes_for_adding, **attr)`, `add_weighted_edges_from(self, ebunch_to_add, weight='weight', **attr)`, `adjacency(self)`<br>An undirected graph class that can store multiedges. |
| **`class NetworkXAlgorithmError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception for unexpected termination of algorithms. |
| **`class NetworkXError`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception for a serious error in NetworkX |
| **`class NetworkXException`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Base class for exceptions in NetworkX. |
| **`class NetworkXNoCycle`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception for algorithms that should return a cycle when running on graphs where such a cycle does not exist. |
| **`class NetworkXNoPath`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception for algorithms that should return a path when running on graphs where such a path does not exist. |
| **`class NetworkXNotImplemented`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised by algorithms not implemented for a type of graph. |
| **`class NetworkXPointlessConcept`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Raised when a null graph is provided as input to an algorithm that cannot use it. |
| **`class NetworkXTreewidthBoundExceeded`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised when a treewidth bound has been provided and it has been exceeded |
| **`class NetworkXUnbounded`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised by algorithms trying to solve a maximization or a minimization problem instance that is unbounded. |
| **`class NetworkXUnfeasible`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised by algorithms trying to solve a problem instance that has no feasible solution. |
| **`class NodeNotFound`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Exception raised if requested node is not present in the graph |
| **`class NotATree`** | `class` · Init: `(...)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Raised when a function expects a tree (that is, a connected undirected graph with no cycles) but gets a non-tree graph as input instead. |
| **`class PlanarEmbedding`** | `class` · Init: `(incoming_graph_data=None, **attr)` · Attrs: `add_edge`, `add_edges_from`, `add_half_edge`, `add_half_edge_ccw`, `add_half_edge_cw`, `add_half_edge_first`, `add_node`, `add_nodes_from`, `add_weighted_edges_from`, `adj` · Methods: `add_edge(self, u_of_edge, v_of_edge, **attr)`, `add_edges_from(self, ebunch_to_add, **attr)`, `add_half_edge(self, start_node, end_node, *, cw=None, ccw=None)`, `add_half_edge_ccw(self, start_node, end_node, reference_neighbor)`, `add_half_edge_cw(self, start_node, end_node, reference_neighbor)`, `add_half_edge_first(self, start_node, end_node)`<br>Represents a planar graph with its planar embedding. |
| **`class PowerIterationFailedConvergence`** | `class` · Init: `(num_iterations, *args, **kw)` · Attrs: `add_note`, `args`, `with_traceback` · Methods: `add_note(self, note, /)`, `with_traceback(self, tb, /)`<br>Raised when the power iteration method fails to converge within a specified iteration limit. |
| **`class SpanningTreeIterator`** | `class` · Init: `(G, weight='weight', minimum=True, ignore_nan=False)` · Attrs: `Partition` · Methods: `Partition(mst_weight: float, partition_dict: dict) -> None`<br>Iterate over all spanning trees of a graph in either increasing or decreasing cost. |
| `adamic_adar_index()` | `function` · Signature: `(G, ebunch=None, *, backend=None, **backend_kwargs)`<br>Compute the Adamic-Adar index of all node pairs in ebunch. |
| `add_cycle()` | `function` · Signature: `(G_to_add_to, nodes_for_cycle, **attr)`<br>Add a cycle to the Graph G_to_add_to. |
| `add_path()` | `function` · Signature: `(G_to_add_to, nodes_for_path, **attr)`<br>Add a path to the Graph G_to_add_to. |
| `add_star()` | `function` · Signature: `(G_to_add_to, nodes_for_star, **attr)`<br>Add a star to Graph G_to_add_to. |
| `adjacency_data()` | `function` · Signature: `(G, attrs={'id': 'id', 'key': 'key'})`<br>Returns data in adjacency format that is suitable for JSON serialization and use in JavaScript documents. |
| `adjacency_graph()` | `function` · Signature: `(data, directed=False, multigraph=True, attrs={'id': 'id', 'key': 'key'}, *, backend=None, **backend_kwargs)`<br>Returns graph from adjacency data format. |
| `adjacency_matrix()` | `function` · Signature: `(G, nodelist=None, dtype=None, weight='weight', *, format='csr', backend=None, **backend_kwargs)`<br>Returns adjacency matrix of `G`. |
| `adjacency_spectrum()` | `function` · Signature: `(G, weight='weight', *, backend=None, **backend_kwargs)`<br>Returns eigenvalues of the adjacency matrix of G. |
| `algebraic_connectivity()` | `function` · Signature: `(G, weight='weight', normalized=False, tol=1e-08, method='tracemin_pcg', seed=None, *, backend=None, **backend_kwargs)`<br>Returns the algebraic connectivity of an undirected graph. |
| `all_neighbors()` | `function` · Signature: `(graph, node)`<br>Returns all of the neighbors of a node in the graph. |
| `all_node_cuts()` | `function` · Signature: `(G, k=None, flow_func=None, *, backend=None, **backend_kwargs)`<br>Returns all minimum k cutsets of an undirected graph G. |
| `all_pairs_all_shortest_paths()` | `function` · Signature: `(G, weight=None, method='dijkstra', *, backend=None, **backend_kwargs)`<br>Compute all shortest paths between all nodes. |
| `all_pairs_bellman_ford_path()` | `function` · Signature: `(G, weight='weight', *, backend=None, **backend_kwargs)`<br>Compute shortest paths between all nodes in a weighted graph. |
| `all_pairs_bellman_ford_path_length()` | `function` · Signature: `(G, weight='weight', *, backend=None, **backend_kwargs)`<br>Compute shortest path lengths between all nodes in a weighted graph. |
| `all_pairs_dijkstra()` | `function` · Signature: `(G, cutoff=None, weight='weight', *, backend=None, **backend_kwargs)`<br>Find shortest weighted paths and lengths between all nodes. |
| `all_pairs_dijkstra_path()` | `function` · Signature: `(G, cutoff=None, weight='weight', *, backend=None, **backend_kwargs)`<br>Compute shortest paths between all nodes in a weighted graph. |
| `all_pairs_dijkstra_path_length()` | `function` · Signature: `(G, cutoff=None, weight='weight', *, backend=None, **backend_kwargs)`<br>Compute shortest path lengths between all nodes in a weighted graph. |
| `all_pairs_lowest_common_ancestor()` | `function` · Signature: `(G, pairs=None, *, backend=None, **backend_kwargs)`<br>Return the lowest common ancestor of all pairs or the provided pairs |
| `all_pairs_node_connectivity()` | `function` · Signature: `(G, nbunch=None, flow_func=None, *, backend=None, **backend_kwargs)`<br>Compute node connectivity between all pairs of nodes of G. |
| `all_pairs_shortest_path()` | `function` · Signature: `(G, cutoff=None, *, backend=None, **backend_kwargs)`<br>Compute shortest paths between all nodes. |
| `all_pairs_shortest_path_length()` | `function` · Signature: `(G, cutoff=None, *, backend=None, **backend_kwargs)`<br>Computes the shortest path lengths between all nodes in `G`. |
| `all_shortest_paths()` | `function` · Signature: `(G, source, target, weight=None, method='dijkstra', *, backend=None, **backend_kwargs)`<br>Compute all shortest simple paths in the graph. |
| `all_simple_edge_paths()` | `function` · Signature: `(G, source, target, cutoff=None, *, backend=None, **backend_kwargs)`<br>Generate lists of edges for all simple paths in G from source to target. |
| `all_simple_paths()` | `function` · Signature: `(G, source, target, cutoff=None, *, backend=None, **backend_kwargs)`<br>Generate all simple paths in the graph G from source to target. |
| `all_topological_sorts()` | `function` · Signature: `(G, *, backend=None, **backend_kwargs)`<br>Returns a generator of _all_ topological sorts of the directed graph G. |
| `all_triads()` | `function` · Signature: `(G, *, backend=None, **backend_kwargs)`<br>A generator of all possible triads in G. |
| `all_triangles()` | `function` · Signature: `(G, nbunch=None, *, backend=None, **backend_kwargs)`<br>Yields all unique triangles in an undirected graph. |
| `ancestors()` | `function` · Signature: `(G, source, *, backend=None, **backend_kwargs)`<br>Returns all nodes having a path to `source` in `G`. |
| `antichains()` | `function` · Signature: `(G, topo_order=None, *, backend=None, **backend_kwargs)`<br>Generates antichains from a directed acyclic graph (DAG). |
| `apply_matplotlib_colors()` | `function` · Signature: `(G, src_attr, dest_attr, map, vmin=None, vmax=None, nodes=True)`<br>Apply colors from a matplotlib colormap to a graph. |
| `approximate_current_flow_betweenness_centrality()` | `function` · Signature: `(G, normalized=True, weight=None, dtype=<class 'float'>, solver='full', epsilon=0.5, kmax=10000, seed=None, *, sample_weight=1, backend=None, **backend_kwargs)`<br>Compute the approximate current-flow betweenness centrality for nodes. |
| `arf_layout()` | `function` · Signature: `(G, pos=None, scaling=1, a=1.1, etol=1e-06, dt=0.001, max_iter=1000, *, seed=None, store_pos_as=None)`<br>Arf layout for networkx |
| `articulation_points()` | `function` · Signature: `(G, *, backend=None, **backend_kwargs)`<br>Yield the articulation points, or cut vertices, of a graph. |
| `astar_path()` | `function` · Signature: `(G, source, target, heuristic=None, weight='weight', *, cutoff=None, backend=None, **backend_kwargs)`<br>Returns a list of nodes in a shortest path between source and target using the A* ("A-star") algorithm. |
| `astar_path_length()` | `function` · Signature: `(G, source, target, heuristic=None, weight='weight', *, cutoff=None, backend=None, **backend_kwargs)`<br>Returns the length of the shortest path between source and target using the A* ("A-star") algorithm. |
| `attr_matrix()` | `function` · Signature: `(G, edge_attr=None, node_attr=None, normalized=False, rc_order=None, dtype=None, order=None, *, backend=None, **backend_kwargs)`<br>Returns the attribute matrix using attributes from `G` as a numpy array. |
| `attr_sparse_matrix()` | `function` · Signature: `(G, edge_attr=None, node_attr=None, normalized=False, rc_order=None, dtype=None, *, backend=None, **backend_kwargs)`<br>Returns a SciPy sparse array using attributes from G. |
| `attracting_components()` | `function` · Signature: `(G, *, backend=None, **backend_kwargs)`<br>Generates the attracting components in `G`. |
| `attribute_assortativity_coefficient()` | `function` · Signature: `(G, attribute, nodes=None, *, backend=None, **backend_kwargs)`<br>Compute assortativity for node attributes. |
| `attribute_mixing_dict()` | `function` · Signature: `(G, attribute, nodes=None, normalized=False, *, backend=None, **backend_kwargs)`<br>Returns dictionary representation of mixing matrix for attribute. |
| `attribute_mixing_matrix()` | `function` · Signature: `(G, attribute, nodes=None, mapping=None, normalized=True, *, backend=None, **backend_kwargs)`<br>Returns mixing matrix for attribute. |
| `average_clustering()` | `function` · Signature: `(G, nodes=None, weight=None, count_zeros=True, *, backend=None, **backend_kwargs)`<br>Compute the average clustering coefficient for the graph G. |
| `average_degree_connectivity()` | `function` · Signature: `(G, source='in+out', target='in+out', nodes=None, weight=None, *, backend=None, **backend_kwargs)`<br>Compute the average degree connectivity of graph. |
| `average_neighbor_degree()` | `function` · Signature: `(G, source='out', target='out', nodes=None, weight=None, *, backend=None, **backend_kwargs)`<br>Returns the average degree of the neighborhood of each node. |
| `average_node_connectivity()` | `function` · Signature: `(G, flow_func=None, *, backend=None, **backend_kwargs)`<br>Returns the average connectivity of a graph G. |
| `average_shortest_path_length()` | `function` · Signature: `(G, weight=None, method=None, *, backend=None, **backend_kwargs)`<br>Returns the average shortest path length. |
| `balanced_tree()` | `function` · Signature: `(r, h, create_using=None, *, backend=None, **backend_kwargs)`<br>Returns the perfectly balanced `r`-ary tree of height `h`. |
| `barabasi_albert_graph()` | `function` · Signature: `(n, m, seed=None, initial_graph=None, *, create_using=None, backend=None, **backend_kwargs)`<br>Returns a random graph using Barabási–Albert preferential attachment |
| `barbell_graph()` | `function` · Signature: `(m1, m2, create_using=None, *, backend=None, **backend_kwargs)`<br>Returns the Barbell Graph: two complete graphs connected by a path. |
| `barycenter()` | `function` · Signature: `(G, weight=None, attr=None, sp=None, *, backend=None, **backend_kwargs)`<br>Calculate centroid of a connected graph, optionally with edge weights. |
| `bellman_ford_path()` | `function` · Signature: `(G, source, target, weight='weight', *, backend=None, **backend_kwargs)`<br>Returns the shortest path from source to target in a weighted graph G. |
| `bellman_ford_path_length()` | `function` · Signature: `(G, source, target, weight='weight', *, backend=None, **backend_kwargs)`<br>Returns the shortest path length from source to target in a weighted graph. |
| `bellman_ford_predecessor_and_distance()` | `function` · Signature: `(G, source, target=None, weight='weight', heuristic=False, *, backend=None, **backend_kwargs)`<br>Compute shortest path lengths and predecessors on shortest paths in weighted graphs. |
| `bethe_hessian_matrix()` | `function` · Signature: `(G, r=None, nodelist=None, *, backend=None, **backend_kwargs)`<br>Returns the Bethe Hessian matrix of G. |
| `bethe_hessian_spectrum()` | `function` · Signature: `(G, r=None, *, backend=None, **backend_kwargs)`<br>Returns eigenvalues of the Bethe Hessian matrix of G. |
| `betweenness_centrality()` | `function` · Signature: `(G, k=None, normalized=True, weight=None, endpoints=False, seed=None, *, backend=None, **backend_kwargs)`<br>Compute the shortest-path betweenness centrality for nodes. |
| `betweenness_centrality_subset()` | `function` · Signature: `(G, sources, targets, normalized=False, weight=None, *, backend=None, **backend_kwargs)`<br>Compute betweenness centrality for a subset of nodes. |
| `bfs_beam_edges()` | `function` · Signature: `(G, source, value, width=None, *, backend=None, **backend_kwargs)`<br>Iterates over edges in a beam search. |
| `bfs_edges()` | `function` · Signature: `(G, source, reverse=False, depth_limit=None, sort_neighbors=None, *, backend=None, **backend_kwargs)`<br>Iterate over edges in a breadth-first-search starting at source. |
| `bfs_labeled_edges()` | `function` · Signature: `(G, sources, *, backend=None, **backend_kwargs)`<br>Iterate over edges in a breadth-first search (BFS) labeled by type. |
| `bfs_layers()` | `function` · Signature: `(G, sources, *, backend=None, **backend_kwargs)`<br>Returns an iterator of all the layers in breadth-first search traversal. |
| `bfs_layout()` | `function` · Signature: `(G, start, *, align='vertical', scale=1, center=None, store_pos_as=None)`<br>Position nodes according to breadth-first search algorithm. |
| `bfs_predecessors()` | `function` · Signature: `(G, source, depth_limit=None, sort_neighbors=None, *, backend=None, **backend_kwargs)`<br>Returns an iterator of predecessors in breadth-first-search from source. |
| `bfs_successors()` | `function` · Signature: `(G, source, depth_limit=None, sort_neighbors=None, *, backend=None, **backend_kwargs)`<br>Returns an iterator of successors in breadth-first-search from source. |
| `bfs_tree()` | `function` · Signature: `(G, source, reverse=False, depth_limit=None, sort_neighbors=None, *, backend=None, **backend_kwargs)`<br>Returns an oriented tree constructed from of a breadth-first-search starting at source. |
| `biconnected_component_edges()` | `function` · Signature: `(G, *, backend=None, **backend_kwargs)`<br>Returns a generator of lists of edges, one list for each biconnected component of the input graph. |
| `biconnected_components()` | `function` · Signature: `(G, *, backend=None, **backend_kwargs)`<br>Returns a generator of sets of nodes, one set for each biconnected component of the graph |
| `bidirectional_dijkstra()` | `function` · Signature: `(G, source, target, weight='weight', *, backend=None, **backend_kwargs)`<br>Dijkstra's algorithm for shortest paths using bidirectional search. |
| `bidirectional_shortest_path()` | `function` · Signature: `(G, source, target, *, backend=None, **backend_kwargs)`<br>Returns a list of nodes in a shortest path between source and target. |
| `binomial_graph()` | `function` · Signature: `(n, p, seed=None, directed=False, *, create_using=None, backend=None, **backend_kwargs)`<br>Returns a $G_{n,p}$ random graph, also known as an Erdős-Rényi graph or a binomial graph. |
| `binomial_tree()` | `function` · Signature: `(n, create_using=None, *, backend=None, **backend_kwargs)`<br>Returns the Binomial Tree of order n. |
| `bipartite_layout()` | `function` · Signature: `(G, nodes=None, align='vertical', scale=1, center=None, aspect_ratio=1.3333333333333333, store_pos_as=None)`<br>Position nodes in two straight lines. |
