

def run():
    # Create graph
    graph = Graph()
    # Add vertices
    graph.add_node(Node("Materials_Ohio_SW Canton", (1,1))) 
    
    graph.add_node(Node("Forging_AAS_Illinois_Chicago", (2,1))) 
    
    graph.add_node(Node("CNC_Lathe_AAS_Michigan_Zeeland",(3,1))) # B
    graph.add_node(Node("CNC_Lathe_AAS_Ohio_Cleveland", (3,2))) # C
    graph.add_node(Node("CNC_Lathe_AAS_Washington_Olympia", (3,3))) # D
    graph.add_node(Node("CNC_Lathe_AAS_Kentucky_Louisville", (3,4))) # D
    graph.add_node(Node("CNC_Lathe_AAS_Pennsylvania_Saxonburg", (3,5))) # D
    graph.add_node(Node("CNC_Lathe_AAS_Pennsylvania_Titusville", (3,6))) # D
    graph.add_node(Node("CNC_Lathe_AAS_Pennsylvania_New Kensington", (3,7))) # D  
    
    graph.add_node(Node("MachineTool_AAS_Michigan_Zeeland",(4,1))) # B
    graph.add_node(Node("MachineTool_AAS_Ohio_Cleveland", (4,2))) # C
    graph.add_node(Node("MachineTool_AAS_Washington_Olympia", (4,3))) # D
    graph.add_node(Node("MachineTool_AAS_Kentucky_Louisville", (4,4))) # D
    graph.add_node(Node("MachineTool_AAS_Pennsylvania_Saxonburg", (4,5))) # D
    graph.add_node(Node("MachineTool_AAS_Ohio_Bowling Green", (4,6))) # D
    graph.add_node(Node("MachineTool_AAS_Pennsylvania_New Kensington", (4,7))) # D
    graph.add_node(Node("MachineTool_AAS_Texas_Navasota", (4,8))) # D
    
    graph.add_node(Node("Grinder_AAS_California_Gardena",(5,1))) # B
    graph.add_node(Node("Grinder_AAS_Pennsylvania_Saxonburg", (5,2))) # C
    graph.add_node(Node("Grinder_AAS_NewYork_Penfield", (5,3))) # D 
    graph.add_node(Node("Grinder_AAS_California_Santa Clara",(5,4)))
    graph.add_node(Node("Grinder_AAS_Pennsylvania_New Kensington",(5,5)))
    graph.add_node(Node("Grinder_AAS_Ohio_Bowling Green",(5,6)))
    
    graph.add_node(Node("CrankShaft_Texas_Arrive", (6,1)))


    
    # Add edges
    graph.add_edge("Materials_Ohio_SW Canton", "Forging_AAS_Illinois_Chicago", location_distance(metal_loc,forging_location)) #S B
    
    graph.add_edge("Forging_AAS_Illinois_Chicago", "CNC_Lathe_AAS_Michigan_Zeeland", location_distance(forging_location, lathe_location[0])) #S B
    graph.add_edge("Forging_AAS_Illinois_Chicago", "CNC_Lathe_AAS_Ohio_Cleveland", location_distance(forging_location, lathe_location[1])) #S D
    graph.add_edge("Forging_AAS_Illinois_Chicago", "CNC_Lathe_AAS_Washington_Olympia", location_distance(forging_location, lathe_location[2])) #S D
    graph.add_edge("Forging_AAS_Illinois_Chicago", "CNC_Lathe_AAS_Kentucky_Louisville", location_distance(forging_location, lathe_location[3])) #S D
    graph.add_edge("Forging_AAS_Illinois_Chicago", "CNC_Lathe_AAS_Pennsylvania_Saxonburg", location_distance(forging_location, lathe_location[4])) #S D
    graph.add_edge("Forging_AAS_Illinois_Chicago", "CNC_Lathe_AAS_Pennsylvania_Titusville", location_distance(forging_location, lathe_location[5])) #S D
    graph.add_edge("Forging_AAS_Illinois_Chicago", "CNC_Lathe_AAS_Pennsylvania_New Kensington", location_distance(forging_location, lathe_location[6])) #S D

    graph.add_edge("CNC_Lathe_AAS_Michigan_Zeeland","Forging_AAS_Illinois_Chicago_Arrive", location_distance(forging_location, lathe_location[0])) #S B
    graph.add_edge("CNC_Lathe_AAS_Ohio_Cleveland", "Forging_AAS_Illinois_Chicago_Arrive", location_distance(forging_location, lathe_location[1])) #S D
    graph.add_edge("CNC_Lathe_AAS_Washington_Olympia", "Forging_AAS_Illinois_Chicago_Arrive", location_distance(forging_location, lathe_location[2])) #S D
    graph.add_edge("CNC_Lathe_AAS_Kentucky_Louisville", "Forging_AAS_Illinois_Chicago_Arrive",  location_distance(forging_location, lathe_location[3])) #S D
    graph.add_edge("CNC_Lathe_AAS_Pennsylvania_Saxonburg", "Forging_AAS_Illinois_Chicago_Arrive", location_distance(forging_location, lathe_location[4])) #S D
    graph.add_edge("CNC_Lathe_AAS_Pennsylvania_Titusville", "Forging_AAS_Illinois_Chicago_Arrive",  location_distance(forging_location, lathe_location[5])) #S D
    graph.add_edge("CNC_Lathe_AAS_Pennsylvania_New Kensington", "Forging_AAS_Illinois_Chicago_Arrive", location_distance(forging_location, lathe_location[6])) #S D
    

    
    # Execute the algorithm
    alg = AStar(graph, "Forging_AAS_Illinois_Chicago", "Forging_AAS_Illinois_Chicago_Arrive")
    path, path_length = alg.search()
    print(" -> ".join(path))
    print(f"Length of the path: {path_length}")

#if __name__ == '__main__':
run()