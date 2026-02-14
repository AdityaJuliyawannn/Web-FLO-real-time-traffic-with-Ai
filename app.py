from flask import Flask, render_template, request, jsonify
import os
import cv2
import numpy as np
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import networkx as nx
import threading
import time
import heapq
import io
from ultralytics import YOLO
import logging
import requests
from collections import deque
from map_integration import create_traffic_map, save_map_to_file, NODE_COORDINATES

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("traffic_monitor.log")
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# =====================================================================
# CONSTANTS AND CONFIGURATION
# =====================================================================

# Load YOLO model
try:
    model = YOLO('yolov8l.pt')
    logger.info("YOLO model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load YOLO model: {str(e)}")
    raise

# Traffic status thresholds
STATUS_THRESHOLDS = {
    'lancar': 5,   # Smooth traffic (≤ 5 vehicles)
    'padat': 15,   # Dense traffic (≤ 15 vehicles)
    'macet': 20    # Congested traffic (> 15 vehicles)
}

# Traffic speed in km/h based on status
TRAFFIC_SPEEDS = {
    'lancar': 35,  # 35 km/h for smooth traffic
    'padat': 20,   # 20 km/h for dense traffic
    'macet': 10    # 10 km/h for congested traffic
}

# Vehicle classes to detect
ALLOWED_VEHICLE_CLASSES = {'car', 'truck', 'bus', 'motorcycle'}

# Vehicle color mapping for visualization
VEHICLE_COLOR_MAP = {
    'car': (0, 255, 0),       # Green
    'truck': (0, 0, 255),     # Red
    'bus': (255, 0, 0),       # Blue
    'motorcycle': (255, 255, 0) # Cyan
}

# CCTV video paths
VIDEO_PATHS = [
    "https://livepantau.semarangkota.go.id/1aee2909-217d-4452-b985-2f59d332b2a9/index.m3u8",  # 0. kalibanteng
    "https://livepantau.semarangkota.go.id/f466ecd6-753b-42f9-8cc8-79b32dfc588c/index.m3u8",  # 1. kaligarang
    "https://livepantau.semarangkota.go.id/22f33ade-5787-47f7-9aec-86da1c8d81ba/index.m3u8",  # 2. madukuro
    "https://livepantau.semarangkota.go.id/cb44a209-58b5-4a7e-99c4-55d5ada0aae2/index.m3u8",  # 3. tugu muda
    "https://livepantau.semarangkota.go.id/6738ac82-c259-46a7-a2aa-0ed7ba24abfe/index.m3u8",  # 4. indraprasta
    "https://livepantau.semarangkota.go.id/c91ef0e4-da38-4673-8a25-6fc4f22ad9da/index.m3u8",  # 5. bergota
    "https://livepantau.semarangkota.go.id/d6e21b78-18f3-488e-ba45-733880536e4f/index.m3u8",  # 6. simp kyai saleh
    "https://livepantau.semarangkota.go.id/31ae4806-c55b-41eb-befd-93c815c09434/index.m3u8",  # 7. Simpang lima
    "https://livepantau.semarangkota.go.id/5f4862ff-ea80-45d4-8baf-fbd025784710/index.m3u8",  # 8. polda
]

# Node positions for graph visualization
POSITIONS = {
    0: (0, 0),
    1: (1, 2),
    2: (2, 0),
    3: (3, 2),
    4: (4, 0),
    5: (5, 2),
    6: (6, 0),
    7: (7, 2),
    8: (8, 1)
}

# Node labels (location names)
NODE_LABELS = {
    0: "Kalibanteng",     # index 0
    1: "Kaligarang",      # index 1  
    2: "Madukuro",        # index 2
    3: "Tugu Muda",       # index 3
    4: "Indraprasta",     # index 4
    5: "Bergota",         # index 5
    6: "Simpang Kyai Saleh", # index 6
    7: "Simpang Lima",    # index 7
    8: "Polda"            # index 8
}

# Edges with actual distances in kilometers
EDGES_WITH_DISTANCE = [
    # ========== TWO-WAY EDGES (Bidirectional) ==========
    # Kalibanteng connections
    (0, 1, 3),  # Kalibanteng -> Kaligarang
    (1, 0, 3),  # Kaligarang -> Kalibanteng
    (0, 2, 1.9),  # Kalibanteng -> Madukuro
    (2, 0, 1.9),  # Madukuro -> Kalibanteng
    
    # Madukuro connections (excluding one-way to Indraprasta)
    (2, 1, 2.9),  # Madukuro -> Kaligarang
    (1, 2, 2),  # Kaligarang -> Madukuro
    (2, 3, 1.2),  # Madukuro -> Tugu Muda
    (3, 2, 1.3),  # Tugu Muda -> Madukuro
    
    # Tugu Muda connections
    (3, 1, 1.9),  # Tugu Muda -> Kaligarang
    (1, 3, 1.9),  # Kaligarang -> Tugu Muda
    (3, 4, 0.7),  # Tugu Muda -> Indraprasta
    (4, 3, 1.3),  # Indraprasta -> Tugu Muda
    (3, 5, 2.3),  # Tugu Muda -> Bergota
    (5, 3, 2.4),  # Bergota -> Tugu Muda
    (3, 6, 0.6),  # Tugu Muda -> Simpang Kyai Saleh
    (6, 3, 0.7),  # Simpang Kyai Saleh -> Tugu Muda
    (3, 8, 3.3),  # Tugu Muda -> Polda
    (8, 3, 3.3),  # Polda -> Tugu Muda
    
    # Bergota connections
    (5, 1, 1.5),  # Bergota -> Kaligarang
    (1, 5, 1.8),  # Kaligarang -> Bergota
    (5, 6, 0.8),  # Bergota -> Simpang Kyai Saleh
    (6, 5, 0.8),  # Simpang Kyai Saleh -> Bergota
    (5, 8, 0.9),  # Bergota -> Polda
    (8, 5, 1.2),  # Polda -> Bergota
    
    # Simpang Kyai Saleh connections (excluding one-way from Indraprasta)
    (6, 7, 1.1),  # Simpang Kyai Saleh -> Simpang Lima
    (7, 6, 1.1),  # Simpang Lima -> Simpang Kyai Saleh
    
    # Simpang Lima connections
    (7, 8, 1.3),  # Simpang Lima -> Polda
    (8, 7, 1.0),  # Polda -> Simpang Lima
    
    # ========== ONE-WAY EDGES ==========
    # ⭐ Polda -> Kaligarang (ONE WAY ONLY)
    (8, 1, 2.1),  # Polda -> Kaligarang (satu arah)
    # Kaligarang -> Polda HARUS lewat Bergota: (1 -> 5 -> 8)
    
    # ⭐ Madukoro -> Indraprasta (ONE WAY ONLY)
    (2, 4, 1.4),  # Madukoro -> Indraprasta (satu arah)
    # Indraprasta -> Madukoro HARUS lewat Tugu Muda: (4 -> 3 -> 2)
    
    # ⭐ Indraprasta -> Simpang Kyai Saleh (ONE WAY ONLY)
    (4, 6, 2.2),  # Indraprasta -> Simpang Kyai Saleh (satu arah)
    # Simpang Kyai Saleh -> Indraprasta HARUS lewat Tugu Muda: (6 -> 3 -> 4)
]

# Extract edges for backward compatibility
EDGES = [(u, v) for u, v, d in EDGES_WITH_DISTANCE]

# Create distance dictionary for quick lookup
EDGE_DISTANCES = {}
for u, v, distance in EDGES_WITH_DISTANCE:
    EDGE_DISTANCES[(u, v)] = distance

# =====================================================================
# VIDEO STREAM HANDLER CLASS
# =====================================================================

class VideoStreamHandler:
    """
    A class to handle video stream processing with robust error handling and frame buffering.
    """
    def __init__(self, video_path, node_id, buffer_size=5, max_retries=10, retry_delay=3, 
                 reconnect_threshold=10, timeout=10):
        """
        Initialize the video stream handler.
        
        Args:
            video_path (str): URL or path to the video stream
            node_id (int): ID of the node/location
            buffer_size (int): Number of frames to buffer
            max_retries (int): Maximum number of connection retry attempts
            retry_delay (int): Delay between retry attempts in seconds
            reconnect_threshold (int): Number of consecutive errors before reconnecting
            timeout (int): Connection timeout in seconds
        """
        self.video_path = video_path
        self.node_id = node_id
        self.buffer_size = buffer_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.reconnect_threshold = reconnect_threshold
        self.timeout = timeout
        
        self.frame_buffer = deque(maxlen=buffer_size)
        self.is_running = True
        self.error_count = 0
        self.total_errors = 0
        self.cap = None
        self.last_frame = self._create_placeholder_frame(f"Starting stream for {NODE_LABELS[node_id]}...")
        
        # Stats tracking
        self.vehicle_count = 0
        self.traffic_status = "lancar"
        
    def _create_placeholder_frame(self, message):
        """Create a placeholder frame with a message when stream is unavailable."""
        height, width = 480, 640
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Add background gradient for better visibility
        for y in range(height):
            color_value = int(180 * (y / height)) + 50
            frame[y, :] = [color_value, color_value, color_value]
            
        # Add text with message
        cv2.putText(frame, NODE_LABELS[self.node_id], (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 160, 255), 2)
        
        cv2.putText(frame, message, (20, height // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                    
        cv2.putText(frame, f"Retrying... ({self.total_errors})", (20, height - 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (50, 50, 255), 2)
                    
        # Add timestamp
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, timestamp, (width - 230, height - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
                    
        return frame
        
    def _init_capture(self):
        """Initialize or reinitialize the video capture with proper error handling."""
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
                
        try:
            # Check if file or URL exists before attempting capture
            if self.video_path.startswith(('http://', 'https://')):
                try:
                    response = requests.head(self.video_path, timeout=self.timeout)
                    if response.status_code >= 400:
                        logger.warning(f"Stream URL returns status code {response.status_code} for node {self.node_id}")
                except Exception as e:
                    logger.warning(f"Cannot connect to stream URL for node {self.node_id}: {str(e)}")
            
            # Initialize capture with a timeout
            self.cap = cv2.VideoCapture(self.video_path)
            
            # Check if capture is successfully opened
            if not self.cap.isOpened():
                logger.error(f"Failed to open video stream for node {self.node_id}")
                self.last_frame = self._create_placeholder_frame("Stream unavailable")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error initializing video capture for node {self.node_id}: {str(e)}")
            self.last_frame = self._create_placeholder_frame(f"Error: {str(e)[:30]}...")
            return False
            
    def _process_frame(self, frame):
        """Process a frame with YOLO detection and add annotations - IMPROVED VERSION."""
        try:
            height, width = frame.shape[:2]
            
            # YOLO Inference
            results = model.predict(frame, stream=True)
            vehicle_count = 0  # Reset vehicle count
            
            # Process detection results
            processed_frame = frame.copy()
            for result in results:
                for box in result.boxes:
                    cls = int(box.cls[0])  # Class ID
                    label = model.names[cls]
                    
                    # Skip non-vehicle classes
                    if label not in ALLOWED_VEHICLE_CLASSES:
                        continue
                        
                    # Extract bounding box coordinates and confidence
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    conf = box.conf[0]
                    vehicle_count += 1
                    
                    # Get color for this vehicle type
                    color = VEHICLE_COLOR_MAP.get(label, (255, 255, 255))
                    
                    # Draw bounding box (thinner line)
                    cv2.rectangle(processed_frame, (x1, y1), (x2, y2), color, 2)
                    
                    # Add label with small background (positioned above box)
                    text = f"{label} {conf:.2f}"
                    (text_width, text_height), baseline = cv2.getTextSize(
                        text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1
                    )
                    
                    # Draw text background (small, above bounding box)
                    cv2.rectangle(
                        processed_frame, 
                        (x1, y1 - text_height - 8), 
                        (x1 + text_width + 4, y1), 
                        color, 
                        -1
                    )
                    
                    # Draw text
                    cv2.putText(
                        processed_frame, text, (x1 + 2, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1
                    )
            
            # Determine traffic status based on vehicle count
            if vehicle_count <= STATUS_THRESHOLDS['lancar']:
                traffic_status = "LANCAR"
                status_color = (0, 255, 0)  # Green
                bg_color = (0, 200, 0)
            elif vehicle_count <= STATUS_THRESHOLDS['padat']:
                traffic_status = "PADAT"
                status_color = (0, 165, 255)  # Orange
                bg_color = (0, 130, 200)
            else:
                traffic_status = "MACET"
                status_color = (0, 0, 255)  # Red
                bg_color = (0, 0, 200)
            
            # Create IMPROVED status overlay - positioned at top, larger and clearer
            overlay_height = 80
            overlay = processed_frame.copy()
            
            # Semi-transparent black background at top
            cv2.rectangle(overlay, (0, 0), (width, overlay_height), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.6, processed_frame, 0.4, 0, processed_frame)
            
            # Location name (top left)
            cv2.putText(
                processed_frame, 
                NODE_LABELS[self.node_id], 
                (15, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.8, 
                (255, 255, 255), 
                2
            )
            
            # Status badge (top center) - LARGER AND MORE VISIBLE
            status_text = f"Status: {traffic_status}"
            (status_width, status_height), _ = cv2.getTextSize(
                status_text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2
            )
            
            status_x = (width - status_width) // 2
            status_y = 50
            
            # Draw status background rectangle
            padding = 10
            cv2.rectangle(
                processed_frame,
                (status_x - padding, status_y - status_height - padding),
                (status_x + status_width + padding, status_y + padding),
                bg_color,
                -1
            )
            
            # Draw status border
            cv2.rectangle(
                processed_frame,
                (status_x - padding, status_y - status_height - padding),
                (status_x + status_width + padding, status_y + padding),
                (255, 255, 255),
                2
            )
            
            # Draw status text (white, bold)
            cv2.putText(
                processed_frame, 
                status_text,
                (status_x, status_y),
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.9, 
                (255, 255, 255), 
                2
            )
            
            # Vehicle count (top right)
            vehicle_text = f"Kendaraan: {vehicle_count}"
            cv2.putText(
                processed_frame, 
                vehicle_text,
                (width - 200, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.7, 
                (255, 255, 255), 
                2
            )
            
            # Add timestamp at bottom right (smaller, unobtrusive)
            timestamp = time.strftime("%H:%M:%S")
            cv2.putText(
                processed_frame, 
                timestamp, 
                (width - 120, height - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.5, 
                (200, 200, 200), 
                1
            )
            
            # Update vehicle count and traffic status
            self.vehicle_count = vehicle_count
            self.traffic_status = traffic_status.lower()
            
            return processed_frame, vehicle_count
            
        except Exception as e:
            logger.error(f"Error processing frame for node {self.node_id}: {str(e)}")
            return frame, 0
    
    def start(self):
        """Start the video processing thread."""
        threading.Thread(target=self._process_video_stream, daemon=True).start()
        
    def _process_video_stream(self):
        """Main processing loop for the video stream with error handling and retry logic."""
        retry_count = 0
        
        while self.is_running and retry_count < self.max_retries:
            # Try to initialize capture
            if not self._init_capture():
                retry_count += 1
                self.total_errors += 1
                logger.warning(f"Failed to initialize capture for node {self.node_id}, "
                               f"retry {retry_count}/{self.max_retries}")
                time.sleep(self.retry_delay)
                continue
                
            # Reset retry count once we have a successful connection
            retry_count = 0
            self.error_count = 0
            
            # Main processing loop for frames
            while self.is_running:
                try:
                    # Read frame with timeout protection
                    ret, frame = self.cap.read()
                    
                    if not ret:
                        self.error_count += 1
                        self.total_errors += 1
                        logger.warning(f"Failed to read frame from node {self.node_id}, "
                                      f"error count: {self.error_count}")
                        
                        # Use the last valid frame from buffer if available
                        if self.frame_buffer:
                            self.last_frame = self.frame_buffer[-1]
                        else:
                            self.last_frame = self._create_placeholder_frame("Connection interrupted")
                            
                        # Check if we need to reconnect
                        if self.error_count >= self.reconnect_threshold:
                            logger.info(f"Reconnecting to stream for node {self.node_id} after "
                                       f"{self.error_count} consecutive errors")
                            break
                            
                        time.sleep(1)
                        continue
                        
                    # Successful frame read, reset error count
                    self.error_count = 0
                    
                    # Process the frame
                    processed_frame, vehicle_count = self._process_frame(frame)
                    
                    # Update the latest frame
                    self.last_frame = processed_frame
                    
                    # Add to buffer
                    self.frame_buffer.append(processed_frame)
                    
                    # Update global traffic graph
                    update_edge_weights(self.node_id, vehicle_count)
                    
                    # Throttle processing to reduce CPU usage
                    time.sleep(0.1)
                    
                except Exception as e:
                    self.error_count += 1
                    self.total_errors += 1
                    logger.error(f"Error in processing stream for node {self.node_id}: {str(e)}")
                    
                    # Create placeholder on error
                    self.last_frame = self._create_placeholder_frame(f"Processing error: {str(e)[:30]}...")
                    
                    # Break out of inner loop to reconnect
                    if self.error_count >= self.reconnect_threshold:
                        break
                        
                    time.sleep(self.retry_delay)
            
            # Clean up capture before retrying
            try:
                if self.cap:
                    self.cap.release()
            except Exception:
                pass
                
            time.sleep(self.retry_delay)
        
        # All retries exhausted
        if retry_count >= self.max_retries:
            logger.error(f"Maximum retry count reached for node {self.node_id}, giving up")
            self.last_frame = self._create_placeholder_frame("Stream unavailable after max retries")
        
    def get_latest_frame(self):
        """Get the latest processed frame."""
        return self.last_frame
        
    def get_vehicle_count(self):
        """Get the current vehicle count."""
        return self.vehicle_count
        
    def get_traffic_status(self):
        """Get the current traffic status."""
        return self.traffic_status
        
    def stop(self):
        """Stop the processing thread."""
        self.is_running = False
        if self.cap:
            self.cap.release()

# =====================================================================
# GRAPH AND ROUTE CALCULATION - A* ALGORITHM
# =====================================================================

# Initialize graph with distances
graph = nx.DiGraph()  
graph.add_nodes_from(POSITIONS.keys())

# Add edges with initial weights based on distance and default speed (lancar)
for u, v, distance in EDGES_WITH_DISTANCE:
    # Initial travel time = distance / speed (in hours), converted to minutes
    initial_travel_time = (distance / TRAFFIC_SPEEDS['lancar']) * 60
    graph.add_edge(u, v, weight=initial_travel_time, distance=distance)

# Traffic status tracking for edges
traffic_status = {edge: "lancar" for edge in graph.edges()}

# Function to update edge weights based on traffic conditions
def update_edge_weights(node_id, vehicle_count):
    """
    Update the edge weights in the graph based on detected vehicle count.
    Menggunakan rumus: waktu tempuh (menit) = jarak (km) / kecepatan (km/jam) * 60
    
    Args:
        node_id (int): The node ID where vehicle count was detected
        vehicle_count (int): Number of vehicles detected
    """
    # Determine traffic status based on vehicle count
    if vehicle_count <= STATUS_THRESHOLDS['lancar']:
        status = 'lancar'
    elif vehicle_count <= STATUS_THRESHOLDS['padat']:
        status = 'padat'
    else:
        status = 'macet'
    
    # Get speed for this traffic status
    speed = TRAFFIC_SPEEDS[status]
    
    # Update weights for all edges connected to this node
    for neighbor in graph.neighbors(node_id):
        # Get the distance for this edge
        edge_key = (node_id, neighbor) if (node_id, neighbor) in EDGE_DISTANCES else (neighbor, node_id)
        distance = EDGE_DISTANCES.get(edge_key, 1.0)
        
        # Calculate travel time in minutes: (distance in km / speed in km/h) * 60
        travel_time = (distance / speed) * 60
        
        # Update the edge weight
        graph[node_id][neighbor]['weight'] = travel_time
        
        # Update traffic status for the edge
        edge = (node_id, neighbor) if (node_id, neighbor) in traffic_status else (neighbor, node_id)
        traffic_status[edge] = status

# =====================================================================
# A* ALGORITHM IMPLEMENTATION
# =====================================================================

def heuristic(node1, node2):
    """
    Calculate the heuristic for A* algorithm.
    Menggunakan jarak Euclidean dari posisi visual dibagi dengan kecepatan maksimum (lancar).
    Heuristic ini admissible karena selalu underestimate waktu tempuh sebenarnya.
    
    Args:
        node1 (int): Starting node ID
        node2 (int): Target node ID
        
    Returns:
        float: Estimated travel time in minutes
    """
    x1, y1 = POSITIONS[node1]
    x2, y2 = POSITIONS[node2]
    euclidean_distance = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
    
    # Normalize Euclidean distance to approximate km (rough scaling factor)
    # Asumsi: 1 unit Euclidean ≈ 1 km dalam skala peta visual
    estimated_distance = euclidean_distance
    
    # Heuristic: waktu minimum jika semua jalur lancar
    # (distance / max_speed) * 60 untuk konversi ke menit
    heuristic_time = (estimated_distance / TRAFFIC_SPEEDS['lancar']) * 60
    
    return heuristic_time

def astar(graph, start, goal):
    """
    Implementation of A* algorithm for finding shortest paths based on travel time.
    
    Args:
        graph (networkx.Graph): The road network graph
        start (int): Starting node ID
        goal (int): Destination node ID
        
    Returns:
        tuple: (dist, prev) where dist is a dict of travel times and prev tracks the path
    """
    # g_score: actual travel time from start to each node (in minutes)
    g_score = {node: float('inf') for node in graph.nodes()}
    g_score[start] = 0
    
    # f_score: estimated total travel time from start to goal through each node
    # f_score = g_score + heuristic
    f_score = {node: float('inf') for node in graph.nodes()}
    f_score[start] = heuristic(start, goal)
    
    # Priority queue: (f_score, node)
    pq = [(f_score[start], start)]
    
    # Track the path
    prev = {node: None for node in graph.nodes()}
    
    # Set of visited nodes
    visited = set()

    while pq:
        current_f, current_node = heapq.heappop(pq)
        
        # If we reached the goal, we're done
        if current_node == goal:
            break
            
        # Skip if already visited
        if current_node in visited:
            continue
            
        visited.add(current_node)
        
        # Explore neighbors
        for neighbor in graph.neighbors(current_node):
            if neighbor in visited:
                continue
                
            # Calculate tentative g_score (actual travel time)
            weight = graph[current_node][neighbor]['weight']
            tentative_g = g_score[current_node] + weight
            
            # If we found a better path to the neighbor
            if tentative_g < g_score[neighbor]:
                prev[neighbor] = current_node
                g_score[neighbor] = tentative_g
                f_score[neighbor] = tentative_g + heuristic(neighbor, goal)
                heapq.heappush(pq, (f_score[neighbor], neighbor))

    return g_score, prev

# Function to recommend best route using A*
def recommend_route(start, end):
    """
    Calculate the recommended route between two nodes using A* algorithm.
    
    Args:
        start (int): Starting node ID
        end (int): Destination node ID
        
    Returns:
        tuple: (path, travel_time) where path is a list of node IDs and travel_time is in minutes
    """
    dist, prev = astar(graph, start, end)
    path = []
    current_node = end
    
    # Reconstruct the path
    while current_node is not None:
        path.append(current_node)
        current_node = prev[current_node]
    path.reverse()
    
    return path, dist[end]

# =====================================================================
# VISUALIZATION
# =====================================================================

# Function to visualize the graph
def visualize_graph(start=0, end=7):
    """
    Create a visualization of the road network graph with the best route highlighted.
    
    Args:
        start (int): Starting node ID
        end (int): Destination node ID
        
    Returns:
        tuple: (graph_image, best_route) where graph_image is a base64 encoded image
    """
    plt.figure(figsize=(12, 7))
    
    # Determine edge colors based on traffic conditions
    edge_colors = []
    edge_widths = []
    for edge in graph.edges(data=True):
        u, v = edge[0], edge[1]
        edge_key = (u, v) if (u, v) in traffic_status else (v, u)
        status = traffic_status.get(edge_key, "lancar")
        
        if status == "lancar":
            edge_colors.append("#3CB371")  # Green
            edge_widths.append(3)
        elif status == "padat":
            edge_colors.append("#FFD700")  # Yellow
            edge_widths.append(4)
        else:  # macet
            edge_colors.append("#FF6347")  # Red
            edge_widths.append(5)

    # Highlight the best route in blue
    best_route, _ = recommend_route(start, end)
    best_edges = [(best_route[i], best_route[i + 1]) for i in range(len(best_route) - 1)]
    
    # Draw graph background
    plt.gca().set_facecolor('#F5F5F5')  # Light gray background
    
    # Draw base nodes and edges
    nx.draw(graph, pos=POSITIONS, with_labels=False, node_size=800, 
            node_color="#B0C4DE", edgecolors='black', linewidths=1.5)
            
    # Draw edges with color coding
    nx.draw_networkx_edges(graph, pos=POSITIONS, edge_color=edge_colors, width=edge_widths)
    
    # Draw best route edges
    if best_edges:
        nx.draw_networkx_edges(graph, pos=POSITIONS, edgelist=best_edges, 
                              edge_color='#4169E1', width=6, alpha=0.8)
                              
    # Draw node labels
    label_positions = {node: (pos[0], pos[1] - 0.1) for node, pos in POSITIONS.items()}
    nx.draw_networkx_labels(graph, pos=label_positions, labels=NODE_LABELS, 
                           font_size=11, font_weight='bold', font_color='black')
    
    # Add traffic status legend
    plt.plot([], [], color="#3CB371", linewidth=3, label='Lancar (35 km/jam)')
    plt.plot([], [], color="#FFD700", linewidth=3, label='Padat (20 km/jam)')
    plt.plot([], [], color="#FF6347", linewidth=3, label='Macet (10 km/jam)')
    plt.plot([], [], color="#4169E1", linewidth=4, label='Rute Terbaik (A*)')
    plt.legend(loc='upper right', frameon=True, facecolor='white', edgecolor='black')
    
    # Mark start and end nodes
    nx.draw_networkx_nodes(graph, pos=POSITIONS, nodelist=[start], 
                          node_color='#32CD32', node_size=900, edgecolors='black')
    nx.draw_networkx_nodes(graph, pos=POSITIONS, nodelist=[end], 
                          node_color='#FF6347', node_size=900, edgecolors='black')
    
    # Add title
    plt.title(f"Rute dari {NODE_LABELS[start]} ke {NODE_LABELS[end]} (A* Algorithm)", 
              fontsize=14, fontweight='bold')
    
    # Remove axis
    plt.axis('off')
    
    # Save plot to a bytes buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    plt.close()
    buf.seek(0)
    
    # Encode the buffer to base64
    graph_image = base64.b64encode(buf.read()).decode('utf-8')
    return graph_image, best_route

# =====================================================================
# FLASK ROUTES
# =====================================================================

# Initialize video stream handlers
stream_handlers = {}

@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html', node_labels=NODE_LABELS)

@app.route('/get_frames')
def get_frames():
    """Return the latest frames from all CCTV streams."""
    encoded_frames = {}
    
    for node_id, handler in stream_handlers.items():
        frame = handler.get_latest_frame()
        
        encoded_frames[node_id] = {
            'image': encode_frame(frame),
            'vehicle_count': handler.get_vehicle_count(),
            'status': handler.get_traffic_status().capitalize()
        }
        
    return jsonify(encoded_frames)

@app.route('/get_interactive_map')
def get_interactive_map():
    """
    Endpoint untuk mendapatkan peta interaktif tanpa route highlighting.
    Menampilkan semua lokasi CCTV dengan status traffic real-time.
    """
    try:
        # Generate peta dengan data real-time
        map_html = create_traffic_map(stream_handlers, graph, traffic_status, route_path=None)
        
        return jsonify({
            'success': True,
            'map_html': map_html
        })
    except Exception as e:
        logger.error(f"Error generating interactive map: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
        
@app.route('/get_route_map', methods=['POST'])
def get_route_map():
    """
    Endpoint untuk mendapatkan peta dengan route highlighting.
    Menampilkan rute terbaik dari start ke end berdasarkan A*.
    """
    try:
        data = request.get_json()
        start_node = int(data['start'])
        end_node = int(data['end'])
        
        # Validasi node IDs
        if start_node not in NODE_COORDINATES or end_node not in NODE_COORDINATES:
            return jsonify({
                'success': False,
                'error': 'Invalid node ID'
            }), 400
        
        # Hitung rute terbaik menggunakan A*
        route_path, total_time = recommend_route(start_node, end_node)
        
        # Generate peta dengan route highlighting
        map_html = create_traffic_map(stream_handlers, graph, traffic_status, route_path=route_path)
        
        # Build route details dengan informasi lengkap
        route_details = []
        total_vehicles = 0
        total_distance_km = 0
        
        for i in range(len(route_path) - 1):
            current = route_path[i]
            next_node = route_path[i + 1]
            
            # Get traffic status for this segment
            edge = (current, next_node) if (current, next_node) in traffic_status else (next_node, current)
            status = traffic_status.get(edge, "lancar")
            
            # Get vehicle count if available
            vehicle_count = 0
            if current in stream_handlers:
                vehicle_count = stream_handlers[current].get_vehicle_count()
                total_vehicles += vehicle_count
            
            # Get distance for this segment
            edge_key = (current, next_node) if (current, next_node) in EDGE_DISTANCES else (next_node, current)
            segment_distance = EDGE_DISTANCES.get(edge_key, 0)
            total_distance_km += segment_distance
            
            # Get speed for this segment
            speed = TRAFFIC_SPEEDS[status]
            
            # Calculate segment time in minutes
            segment_time = (segment_distance / speed) * 60
            
            route_details.append({
                'from': NODE_COORDINATES[current]['name'],
                'to': NODE_COORDINATES[next_node]['name'],
                'status': status,
                'vehicle_count': vehicle_count,
                'distance_km': round(segment_distance, 2),
                'speed_kmh': speed,
                'time_minutes': round(segment_time, 1)
            })
        
        return jsonify({
            'success': True,
            'map_html': map_html,
            'route_details': route_details,
            'route_nodes': [NODE_COORDINATES[node]['name'] for node in route_path],
            'total_distance': round(total_distance_km, 2),
            'estimated_time': round(total_time, 1),
            'total_vehicles': total_vehicles
        })
        
    except Exception as e:
        logger.error(f"Error generating route map: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Helper function to encode a frame to base64
def encode_frame(frame):
    """
    Encode a frame as base64 for transmission to the client.
    
    Args:
        frame (numpy.ndarray): The frame to encode
        
    Returns:
        str: Base64 encoded JPEG image
    """
    if frame is None:
        # Return a black frame if no frame is available
        black_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        _, buffer = cv2.imencode(".jpg", black_frame)
    else:
        # Resize frame for better performance
        resized_frame = cv2.resize(frame, (640, 480))
        _, buffer = cv2.imencode(".jpg", resized_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    
    return base64.b64encode(buffer).decode('utf-8')

@app.route('/save_current_map')
def save_current_map():
    """
    Endpoint untuk menyimpan snapshot peta saat ini ke file HTML.
    Berguna untuk dokumentasi atau analisis.
    """
    try:
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'traffic_map_{timestamp}.html'
        
        save_map_to_file(stream_handlers, graph, traffic_status, route_path=None, filename=filename)
        
        return jsonify({
            'success': True,
            'message': f'Map saved to {filename}',
            'filename': filename
        })
    except Exception as e:
        logger.error(f"Error saving map: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/get_traffic_summary')
def get_traffic_summary():
    """
    Endpoint untuk mendapatkan ringkasan status traffic di semua lokasi.
    Berguna untuk dashboard atau monitoring cepat.
    """
    try:
        summary = {
            'locations': [],
            'total_vehicles': 0,
            'lancar_count': 0,
            'padat_count': 0,
            'macet_count': 0
        }
        
        for node_id, handler in stream_handlers.items():
            if node_id not in NODE_COORDINATES:
                continue
                
            vehicle_count = handler.get_vehicle_count()
            status = handler.get_traffic_status()
            
            summary['locations'].append({
                'node_id': node_id,
                'name': NODE_COORDINATES[node_id]['name'],
                'vehicle_count': vehicle_count,
                'status': status,
                'lat': NODE_COORDINATES[node_id]['lat'],
                'lon': NODE_COORDINATES[node_id]['lon']
            })
            
            summary['total_vehicles'] += vehicle_count
            
            if status == 'lancar':
                summary['lancar_count'] += 1
            elif status == 'padat':
                summary['padat_count'] += 1
            else:
                summary['macet_count'] += 1
        
        return jsonify(summary)
        
    except Exception as e:
        logger.error(f"Error generating traffic summary: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_edge_info')
def get_edge_info():
    """
    Endpoint untuk mendapatkan informasi detail tentang semua edge/ruas jalan.
    Berguna untuk debugging dan monitoring detail.
    """
    try:
        edge_info = []
        
        for u, v, data in graph.edges(data=True):
            edge_key = (u, v) if (u, v) in traffic_status else (v, u)
            status = traffic_status.get(edge_key, "lancar")
            distance = data.get('distance', 0)
            weight = data.get('weight', 0)
            speed = TRAFFIC_SPEEDS[status]
            
            edge_info.append({
                'from': NODE_LABELS[u],
                'to': NODE_LABELS[v],
                'from_id': u,
                'to_id': v,
                'distance_km': round(distance, 2),
                'travel_time_minutes': round(weight, 1),
                'status': status,
                'speed_kmh': speed
            })
        
        return jsonify({
            'success': True,
            'edges': edge_info,
            'total_edges': len(edge_info)
        })
        
    except Exception as e:
        logger.error(f"Error getting edge info: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/get_graph_visualization', methods=['POST'])
def get_graph_visualization():
    """
    Endpoint untuk mendapatkan visualisasi graph dengan matplotlib.
    """
    try:
        data = request.get_json()
        start_node = int(data.get('start', 0))
        end_node = int(data.get('end', 7))
        
        # Generate visualization
        graph_image, best_route = visualize_graph(start_node, end_node)
        
        # Get route info
        _, total_time = recommend_route(start_node, end_node)
        
        return jsonify({
            'success': True,
            'graph_image': graph_image,
            'best_route': [NODE_LABELS[node] for node in best_route],
            'estimated_time': round(total_time, 1)
        })
        
    except Exception as e:
        logger.error(f"Error generating graph visualization: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/compare_routes', methods=['POST'])
def compare_routes():
    """
    Endpoint untuk membandingkan beberapa rute alternatif.
    Berguna untuk menunjukkan perbedaan waktu tempuh antar rute.
    """
    try:
        data = request.get_json()
        start_node = int(data['start'])
        end_node = int(data['end'])
        
        # Hitung rute terbaik dengan A*
        best_route, best_time = recommend_route(start_node, end_node)
        
        # Hitung semua possible paths (untuk perbandingan)
        # Menggunakan NetworkX untuk mencari beberapa rute alternatif
        try:
            all_simple_paths = list(nx.all_simple_paths(graph, start_node, end_node, cutoff=6))
            
            routes_comparison = []
            
            for path in all_simple_paths[:5]:  # Ambil maksimal 5 rute untuk perbandingan
                total_time = 0
                total_distance = 0
                
                for i in range(len(path) - 1):
                    current = path[i]
                    next_node = path[i + 1]
                    
                    # Get edge weight (travel time)
                    weight = graph[current][next_node]['weight']
                    total_time += weight
                    
                    # Get edge distance
                    edge_key = (current, next_node) if (current, next_node) in EDGE_DISTANCES else (next_node, current)
                    distance = EDGE_DISTANCES.get(edge_key, 0)
                    total_distance += distance
                
                routes_comparison.append({
                    'route': [NODE_LABELS[node] for node in path],
                    'route_ids': path,
                    'total_time': round(total_time, 1),
                    'total_distance': round(total_distance, 2),
                    'is_best': path == best_route
                })
            
            # Sort by travel time
            routes_comparison.sort(key=lambda x: x['total_time'])
            
            return jsonify({
                'success': True,
                'routes': routes_comparison,
                'best_route_index': next((i for i, r in enumerate(routes_comparison) if r['is_best']), 0)
            })
            
        except nx.NetworkXNoPath:
            return jsonify({
                'success': False,
                'error': 'No path exists between the selected nodes'
            }), 400
        
    except Exception as e:
        logger.error(f"Error comparing routes: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# =====================================================================
# APPLICATION INITIALIZATION
# =====================================================================

def initialize_system():
    """Initialize the entire monitoring system."""
    logger.info("Initializing traffic monitoring system...")
    logger.info(f"Traffic speeds configured: Lancar={TRAFFIC_SPEEDS['lancar']} km/h, "
                f"Padat={TRAFFIC_SPEEDS['padat']} km/h, Macet={TRAFFIC_SPEEDS['macet']} km/h")
    
    # Initialize stream handlers for each CCTV location
    for node_id, video_path in enumerate(VIDEO_PATHS):
        logger.info(f"Initializing stream for node {node_id}: {NODE_LABELS[node_id]}")
        handler = VideoStreamHandler(video_path, node_id)
        stream_handlers[node_id] = handler
        handler.start()
        
    logger.info("All video streams initialized")
    logger.info(f"Total edges in graph: {len(graph.edges())}")
    logger.info(f"Total nodes in graph: {len(graph.nodes())}")

if __name__ == '__main__':
    # Initialize the system
    initialize_system()
    
    # Log edge information
    logger.info("Edge information:")
    for u, v, data in graph.edges(data=True):
        distance = data.get('distance', 0)
        weight = data.get('weight', 0)
        logger.info(f"  {NODE_LABELS[u]} -> {NODE_LABELS[v]}: {distance} km, "
                   f"initial travel time: {weight:.1f} minutes")
    
    # Start the Flask application
    logger.info("Starting Flask web server...")
    app.run(debug=True, threaded=True, host='0.0.0.0')
    
    # Cleanup on exit
    for handler in stream_handlers.values():
        handler.stop()
