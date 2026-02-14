import folium # type: ignore
from folium import plugins # type: ignore
import logging
import requests
from functools import lru_cache

logger = logging.getLogger(__name__)

# Koordinat lokasi CCTV di Semarang (dalam format lat, lon)
NODE_COORDINATES = {
    0: {  # Kalibanteng
        'name': 'Kalibanteng',
        'lat': -6.9845739281732975,
        'lon': 110.38351440522527
    },
    1: {  # Kaligarang  
        'name': 'Kaligarang',
        'lat': -6.995766634139341,
        'lon': 110.40231267560914
    },
    2: {  # Madukuro
        'name': 'Madukuro', 
        'lat': -6.98070456033708,
        'lon': 110.40003054307869
    },
    3: {  # Tugu Muda
        'name': 'Tugu Muda',
        'lat': -6.983909377988807,
        'lon': 110.4094973768135
    },
    4: {  # Indraprasta
        'name': 'Indraprasta',
        'lat': -6.97857137309681,
        'lon': 110.41163595541559
    },
    5: {  # Bergota
        'name': 'Bergota',
        'lat': -6.993292725367926,
        'lon': 110.4137406704881
    },
    6: {  # Simpang Kyai Saleh
        'name': 'Simpang Kyai Saleh',
        'lat': -6.986660206981591,
        'lon': 110.41393529540247
    },
    7: {  # Simpang lima
        'name': 'Simpang Lima',
        'lat': -6.989453409357332,
        'lon': 110.42248309240397
    },
    8: { #Polda
        'name': 'Polda',
        'lat': -6.99734554026615,
        'lon': 110.41946265584971
    }
}

# Warna berdasarkan status traffic
TRAFFIC_COLORS = {
    'lancar': '#10b981',   # Green (modern)
    'padat': '#f59e0b',    # Amber
    'macet': '#ef4444'     # Red (modern)
}

# Strategic waypoints untuk area kompleks (bundaran, persimpangan besar)
# Strategic waypoints untuk area kompleks (bundaran, persimpangan besar)
# Format: (node1, node2): [{'lat': x, 'lon': y}, ...]
STRATEGIC_WAYPOINTS = {
    # ========== BUNDARAN TUGU MUDA ==========
    
    # 1. Madukoro (2) → Tugu Muda (3)
    (2, 3): [
        {'lat': -6.9839038931532755, 'lon': 110.40812520445667},  # Waypoint masuk bundaran dari Madukoro
    ],
    
    # 2. Tugu Muda (3) → Indraprasta (4)
    (3, 4): [
        {'lat': -6.9804871268179935, 'lon': 110.41070275232582},  # Waypoint keluar ke Indraprasta
    ],
    
    # 3. Indraprasta (4) → Tugu Muda (3) [ARAH BALIK]
    (4, 3): [
        {'lat': -6.9801898260806405, 'lon': 110.41369796048141},  # Waypoint masuk bundaran dari Indraprasta
    ],
    
    # 4. Tugu Muda (3) → Simpang Kyai Saleh (6)
    (3, 6): [
        {'lat': -6.984843207496373, 'lon': 110.4101688238629},  # Waypoint keluar ke Simpang Kyai Saleh
    ],
    
    # 5. Simpang Kyai Saleh (6) → Tugu Muda (3) [ARAH BALIK]
    (6, 3): [
        {'lat': -6.984843207496373, 'lon': 110.4101688238629},  # Waypoint masuk bundaran (sama dengan keluar)
    ],
    
    # 6. Tugu Muda (3) → Bergota (5)
    (3, 5): [
        {'lat': -6.984881985410595, 'lon': 110.40951769157611},  # Waypoint keluar ke Bergota
    ],
    
    # 7. Bergota (5) → Tugu Muda (3) [ARAH BALIK]
    (5, 3): [
        {'lat': -6.984881985410595, 'lon': 110.40951769157611},  # Waypoint masuk bundaran (sama dengan keluar)
    ],
    
    # 8. Tugu Muda (3) → Kaligarang (1)
    (3, 1): [
        {'lat': -6.984881985410595, 'lon': 110.40951769157611},  # Waypoint keluar ke Kaligarang (sama dengan Bergota)
    ],
    
    # 9. Kaligarang (1) → Tugu Muda (3) [ARAH BALIK]
    (1, 3): [
        {'lat': -6.984881985410595, 'lon': 110.40951769157611},  # Waypoint masuk bundaran
    ],
    
    # ========== RUTE MADUKORO - INDRAPRASTA (LURUS) ==========
    
    # Madukoro (2) → Indraprasta (4) - jalan lurus
    (2, 4): [
        {'lat': -6.979500, 'lon': 110.40550},  # Waypoint 1: Tengah jalan lurus
        {'lat': -6.978700, 'lon': 110.40900},  # Waypoint 2: Mendekati Indraprasta
    ],
    
    # Indraprasta (4) → Madukoro (2) [ARAH BALIK]
    (4, 2): [
        {'lat': -6.978700, 'lon': 110.40900},  # Waypoint 1: Keluar dari Indraprasta
        {'lat': -6.979500, 'lon': 110.40550},  # Waypoint 2: Tengah jalan
    ],
    
    # ========== RUTE BERGOTA - SIMPANG KYAI SALEH ==========
    
    # Bergota (5) → Simpang Kyai Saleh (6) - jalan lurus
    (5, 6): [
        {'lat': -6.989345757693151, 'lon': 110.41409050312883},  # Waypoint di tengah jalan lurus
    ],
    
    # Simpang Kyai Saleh (6) → Bergota (5) [ARAH BALIK]
    (6, 5): [
        {'lat': -6.989345757693151, 'lon': 110.41409050312883},
    ],
    
    # ========== RUTE BERGOTA - SIMPANG LIMA ==========
    
    # Bergota (5) → Simpang Lima (7)
    (5, 7): [
        {'lat': -6.991000, 'lon': 110.418000},  # Waypoint langsung ke Simpang Lima
    ],
    
    # Simpang Lima (7) → Bergota (5) [ARAH BALIK]
    (7, 5): [
        {'lat': -6.991000, 'lon': 110.418000},
    ],

    # ========== MADUKORO - KALIGARANG ==========
    (1, 2): [
        {'lat': -6.987697441900785, 'lon': 110.4026861048388},
    ],

    (2, 1): [
        {'lat': -6.9906048464098545, 'lon': 110.40196740324615},
    ],
}

# Daftar edge yang sebaiknya menggunakan straight line (jarak pendek & jelas)
# Untuk menghindari routing yang berlebihan
FORCE_STRAIGHT_LINE = {
    (5, 6), (6, 5),  # Bergota - Kyai Saleh (jalan lurus)
    # (2, 4), (4, 2),  # DINONAKTIFKAN - sekarang pakai STRATEGIC_WAYPOINTS yang lebih detail
}

@lru_cache(maxsize=512)
def get_osrm_route_with_waypoints(coordinates_tuple):
    """
    Get route geometry from OSRM API with support for multiple waypoints.
    Uses tuple of coordinates for caching.
    
    Args:
        coordinates_tuple: tuple of (lon, lat) pairs
        
    Returns:
        list: Route coordinates [[lat, lon], ...] or None if failed
    """
    try:
        # Build coordinates string for OSRM
        coords_str = ';'.join([f"{lon},{lat}" for lon, lat in coordinates_tuple])
        
        url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}"
        params = {
            'overview': 'full',
            'geometries': 'geojson',
            'continue_straight': 'false'  # Allow turns at waypoints
        }
        
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('routes') and len(data['routes']) > 0:
                coords = data['routes'][0]['geometry']['coordinates']
                route_coords = [[lat, lon] for lon, lat in coords]
                return route_coords
        
        logger.debug(f"OSRM routing failed: {response.status_code}")
        return None
        
    except Exception as e:
        logger.debug(f"OSRM error: {str(e)}")
        return None


def get_route_geometry(lat1, lon1, lat2, lon2, node1=None, node2=None):
    """
    Get route geometry using OSRM with optional strategic waypoints.
    
    Args:
        lat1, lon1: Starting coordinates
        lat2, lon2: Ending coordinates
        node1, node2: Node IDs for checking strategic waypoints
        
    Returns:
        list: Route coordinates [[lat, lon], ...]
    """
    # Check if we have strategic waypoints for this route
    waypoints = []
    if node1 is not None and node2 is not None:
        edge_key = (node1, node2)
        if edge_key in STRATEGIC_WAYPOINTS:
            waypoints = STRATEGIC_WAYPOINTS[edge_key]
            logger.info(f"🎯 Using {len(waypoints)} strategic waypoint(s) for route {node1} -> {node2}")
    
    # Build coordinate tuple for OSRM
    coords = [(lon1, lat1)]
    for wp in waypoints:
        coords.append((wp['lon'], wp['lat']))
    coords.append((lon2, lat2))
    
    # Convert to tuple for caching
    coords_tuple = tuple(coords)
    
    # Try OSRM with waypoints
    route = get_osrm_route_with_waypoints(coords_tuple)
    
    if route and len(route) > 1:
        logger.info(f"✅ OSRM routing successful with {len(route)} points for {node1} -> {node2}")
        return route
    
    # Fallback: try without waypoints if with waypoints failed
    if len(waypoints) > 0:
        logger.warning(f"⚠️ Waypoint routing failed, trying direct route for {node1} -> {node2}")
        simple_coords = ((lon1, lat1), (lon2, lat2))
        route = get_osrm_route_with_waypoints(simple_coords)
        if route and len(route) > 1:
            return route
    
    # Final fallback to straight line
    logger.debug(f"ℹ️ Using fallback straight line for {node1} -> {node2}")
    return [[lat1, lon1], [lat2, lon2]]


def create_traffic_map(stream_handlers, graph, traffic_status, route_path=None, zoom_start=13):
    """
    Create an interactive traffic map using Folium with improved routing and styling.
    
    Args:
        stream_handlers (dict): Dictionary of video stream handlers
        graph (networkx.Graph): Road network graph
        traffic_status (dict): Current traffic status for edges
        route_path (list, optional): List of nodes representing the optimal route
        zoom_start (int): Initial zoom level for the map
        
    Returns:
        str: HTML string of the generated map
    """
    try:
        # Calculate center of Semarang from our node coordinates
        center_lat = sum(coord['lat'] for coord in NODE_COORDINATES.values()) / len(NODE_COORDINATES)
        center_lon = sum(coord['lon'] for coord in NODE_COORDINATES.values()) / len(NODE_COORDINATES)
        
        # Create base map with modern style
        traffic_map = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom_start,
            tiles='CartoDB Positron',
            zoom_control=True,
            scrollWheelZoom=True,
            dragging=True
        )
        
        # Add alternative tile layers
        folium.TileLayer(
            'OpenStreetMap',
            name='Street Map'
        ).add_to(traffic_map)
        
        folium.TileLayer(
            'CartoDB Dark_Matter', 
            name='Dark Map'
        ).add_to(traffic_map)
        
        # Add road network edges with traffic-based coloring using OSRM routing
        for edge in graph.edges(data=True):
            node1, node2, data = edge
            
            # Skip if nodes not in our coordinate system
            if node1 not in NODE_COORDINATES or node2 not in NODE_COORDINATES:
                continue
                
            # Get coordinates for both nodes
            coord1 = NODE_COORDINATES[node1]
            coord2 = NODE_COORDINATES[node2]
            
            # Determine edge status and color
            edge_key = (node1, node2) if (node1, node2) in traffic_status else (node2, node1)
            status = traffic_status.get(edge_key, 'lancar')
            color = TRAFFIC_COLORS.get(status, '#6b7280')
            
            # Set line weight based on traffic density
            weight = {'lancar': 4, 'padat': 6, 'macet': 8}.get(status, 4)
            opacity = {'lancar': 0.7, 'padat': 0.8, 'macet': 0.9}.get(status, 0.7)
            
            # Get realistic route coordinates using OSRM with waypoints
            route_coords = get_route_geometry(
                coord1['lat'], coord1['lon'],
                coord2['lat'], coord2['lon'],
                node1, node2
            )
            
            # Create edge line following roads
            folium.PolyLine(
                locations=route_coords,
                color=color,
                weight=weight,
                opacity=opacity,
                smooth_factor=1.5,
                popup=folium.Popup(
                    f"""<div style="font-family: system-ui;">
                        <strong>{coord1['name']}</strong> ↔ <strong>{coord2['name']}</strong><br>
                        <span style="color: {color}; font-weight: bold;">● {status.upper()}</span>
                    </div>""",
                    max_width=200
                )
            ).add_to(traffic_map)
        
        # Highlight optimal route if provided
        if route_path and len(route_path) > 1:
            logger.info(f"🚀 Building optimal route visualization with {len(route_path)} nodes")
            # Build complete route following roads with OSRM
            complete_route_coords = []
            
            for i in range(len(route_path) - 1):
                node1 = route_path[i]
                node2 = route_path[i + 1]
                
                if node1 in NODE_COORDINATES and node2 in NODE_COORDINATES:
                    coord1 = NODE_COORDINATES[node1]
                    coord2 = NODE_COORDINATES[node2]
                    
                    # Get segment route using OSRM with waypoints
                    segment_coords = get_route_geometry(
                        coord1['lat'], coord1['lon'],
                        coord2['lat'], coord2['lon'],
                        node1, node2
                    )
                    
                    # Add segment coordinates (avoid duplicates at connection points)
                    if i == 0:
                        complete_route_coords.extend(segment_coords)
                    else:
                        # Skip first point if it's very close to last added point
                        if len(complete_route_coords) > 0 and len(segment_coords) > 0:
                            last_point = complete_route_coords[-1]
                            first_point = segment_coords[0]
                            distance = ((last_point[0] - first_point[0])**2 + (last_point[1] - first_point[1])**2)**0.5
                            if distance < 0.0001:  # Very close, skip duplicate
                                complete_route_coords.extend(segment_coords[1:])
                            else:
                                complete_route_coords.extend(segment_coords)
                        else:
                            complete_route_coords.extend(segment_coords)
            
            if len(complete_route_coords) > 1:
                logger.info(f"✅ Route visualization complete with {len(complete_route_coords)} coordinate points")
                # Main route line (thicker, solid)
                folium.PolyLine(
                    locations=complete_route_coords,
                    color='#3b82f6',
                    weight=6,
                    opacity=0.8,
                    smooth_factor=1.5,
                    popup='<strong style="color: #3b82f6;">🛣️ Rute Optimal (A*)</strong>'
                ).add_to(traffic_map)
                
                # Animated overlay (thinner, dashed)
                folium.PolyLine(
                    locations=complete_route_coords,
                    color='#ffffff',
                    weight=2,
                    opacity=0.9,
                    dash_array='10, 15',
                    smooth_factor=1.5
                ).add_to(traffic_map)
        
        # Add CCTV location markers with improved design
        for node_id, coordinates in NODE_COORDINATES.items():
            # Get real-time data from stream handlers
            vehicle_count = 0
            status = 'lancar'
            
            if node_id in stream_handlers:
                vehicle_count = stream_handlers[node_id].get_vehicle_count()
                status = stream_handlers[node_id].get_traffic_status()
            
            # Create modern marker icon
            marker_color = TRAFFIC_COLORS.get(status, '#6b7280')
            icon_html = f'''
            <div style="
                position: relative;
                display: flex;
                align-items: center;
                justify-content: center;
            ">
                <div style="
                    background: linear-gradient(135deg, {marker_color} 0%, {marker_color}dd 100%);
                    color: white;
                    border-radius: 50%;
                    width: 40px;
                    height: 40px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                    font-size: 14px;
                    border: 3px solid white;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.25);
                    font-family: system-ui;
                ">
                    {vehicle_count}
                </div>
                <div style="
                    position: absolute;
                    top: -8px;
                    right: -8px;
                    background-color: white;
                    border-radius: 50%;
                    width: 20px;
                    height: 20px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.2);
                    font-size: 10px;
                ">
                    📹
                </div>
            </div>
            '''
            
            # Create modern popup content
            popup_content = f"""
            <div style="width: 220px; font-family: system-ui; padding: 4px;">
                <div style="
                    background: linear-gradient(135deg, {marker_color} 0%, {marker_color}dd 100%);
                    color: white;
                    padding: 12px;
                    margin: -10px -10px 10px -10px;
                    border-radius: 8px 8px 0 0;
                    font-weight: 600;
                    font-size: 16px;
                ">
                    📹 {coordinates['name']}
                </div>
                <div style="padding: 8px 4px;">
                    <div style="display: flex; align-items: center; margin: 8px 0;">
                        <div style="
                            width: 12px; 
                            height: 12px; 
                            background-color: {marker_color}; 
                            border-radius: 50%;
                            margin-right: 8px;
                        "></div>
                        <strong>Status:</strong>
                        <span style="margin-left: 8px; color: {marker_color}; font-weight: 600; text-transform: uppercase;">
                            {status}
                        </span>
                    </div>
                    <div style="margin: 8px 0;">
                        <strong>🚗 Kendaraan:</strong> 
                        <span style="font-size: 18px; font-weight: 600; color: {marker_color};">{vehicle_count}</span>
                    </div>
                    <div style="margin-top: 12px; padding-top: 8px; border-top: 1px solid #e5e7eb; font-size: 11px; color: #6b7280;">
                        📍 {coordinates['lat']:.5f}°, {coordinates['lon']:.5f}°
                    </div>
                </div>
            </div>
            """
            
            # Add marker to map
            folium.Marker(
                location=[coordinates['lat'], coordinates['lon']],
                popup=folium.Popup(popup_content, max_width=250),
                tooltip=f"<strong>{coordinates['name']}</strong><br>{status.upper()} • {vehicle_count} kendaraan",
                icon=folium.DivIcon(html=icon_html, class_name="custom-marker")
            ).add_to(traffic_map)
            
            # Special markers for route start and end
            if route_path:
                if node_id == route_path[0]:  # Start node
                    folium.Marker(
                        location=[coordinates['lat'], coordinates['lon']],
                        popup=f"<strong>🚀 Titik Awal</strong><br>{coordinates['name']}",
                        icon=folium.Icon(color='green', icon='play', prefix='fa'),
                        z_index_offset=1000
                    ).add_to(traffic_map)
                elif node_id == route_path[-1]:  # End node
                    folium.Marker(
                        location=[coordinates['lat'], coordinates['lon']],
                        popup=f"<strong>🏁 Tujuan</strong><br>{coordinates['name']}",
                        icon=folium.Icon(color='red', icon='flag-checkered', prefix='fa'),
                        z_index_offset=1000
                    ).add_to(traffic_map)
        
        # Add modern traffic legend
        legend_html = '''
        <div style="
            position: fixed; 
            top: 10px; 
            right: 10px; 
            width: 200px; 
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            z-index: 9999; 
            font-family: system-ui;
            overflow: hidden;
        ">
            <div style="
                background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
                color: white;
                padding: 12px 16px;
                font-weight: 600;
                font-size: 15px;
            ">
                🚦 Status Lalu Lintas
            </div>
            <div style="padding: 12px 16px;">
                <div style="display: flex; align-items: center; margin: 10px 0;">
                    <div style="width: 28px; height: 5px; background-color: #10b981; border-radius: 3px; margin-right: 10px;"></div>
                    <span style="font-size: 14px;">Lancar</span>
                </div>
                <div style="display: flex; align-items: center; margin: 10px 0;">
                    <div style="width: 28px; height: 5px; background-color: #f59e0b; border-radius: 3px; margin-right: 10px;"></div>
                    <span style="font-size: 14px;">Padat</span>
                </div>
                <div style="display: flex; align-items: center; margin: 10px 0;">
                    <div style="width: 28px; height: 5px; background-color: #ef4444; border-radius: 3px; margin-right: 10px;"></div>
                    <span style="font-size: 14px;">Macet</span>
                </div>'''
        
        if route_path:
            legend_html += '''
                <hr style="margin: 12px 0; border: none; border-top: 1px solid #e5e7eb;">
                <div style="display: flex; align-items: center; margin: 10px 0;">
                    <div style="width: 28px; height: 5px; background-color: #3b82f6; border-radius: 3px; margin-right: 10px;"></div>
                    <span style="font-size: 14px; font-weight: 500;">Rute Optimal</span>
                </div>'''
            
        legend_html += '''
            </div>
        </div>'''
        
        traffic_map.get_root().html.add_child(folium.Element(legend_html))
        
        # Add layer control
        folium.LayerControl().add_to(traffic_map)
        
        # Add fullscreen button
        plugins.Fullscreen(
            position='topleft',
            title='Layar Penuh',
            title_cancel='Keluar Layar Penuh'
        ).add_to(traffic_map)
        
        # Add measure control for distance measurement
        plugins.MeasureControl(
            position='topleft',
            primary_length_unit='kilometers',
            secondary_length_unit='meters',
            primary_area_unit='hectares'
        ).add_to(traffic_map)
        
        # Add mini map
        plugins.MiniMap(
            toggle_display=True,
            tile_layer='CartoDB Positron'
        ).add_to(traffic_map)
        
        # Generate HTML
        map_html = traffic_map._repr_html_()
        
        logger.info("Interactive traffic map generated successfully with OSRM routing and strategic waypoints")
        return map_html
        
    except Exception as e:
        logger.error(f"Error creating traffic map: {str(e)}")
        error_html = f"""
        <div style="
            display: flex; 
            justify-content: center; 
            align-items: center; 
            height: 400px; 
            background: linear-gradient(135deg, #fef3c7 0%, #fee2e2 100%);
            border-radius: 12px;
            font-family: system-ui;
        ">
            <div style="text-align: center; padding: 32px;">
                <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
                <h3 style="color: #dc2626; margin: 0 0 8px 0;">Error Loading Map</h3>
                <p style="color: #991b1b; margin: 8px 0;">{str(e)}</p>
                <p style="font-size: 12px; color: #78716c; margin-top: 16px;">
                    Silakan periksa log server untuk detail lebih lanjut
                </p>
            </div>
        </div>
        """
        return error_html


def save_map_to_file(stream_handlers, graph, traffic_status, route_path=None, filename='traffic_map.html'):
    """
    Save the current traffic map to an HTML file.
    """
    try:
        map_html = create_traffic_map(stream_handlers, graph, traffic_status, route_path)
        timestamp = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Traffic Map - {timestamp}</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    margin: 0;
                    font-family: system-ui, -apple-system, sans-serif;
                }}
                .header {{
                    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
                    color: white;
                    padding: 20px;
                    text-align: center;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }}
                .header h2 {{
                    margin: 0 0 8px 0;
                    font-size: 24px;
                }}
                .header p {{
                    margin: 0;
                    opacity: 0.9;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>🚦 Peta Lalu Lintas Semarang</h2>
                <p>📅 {timestamp}</p>
            </div>
            {map_html}
        </body>
        </html>
        """
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(full_html)
            
        logger.info(f"Traffic map saved to {filename}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving map to file: {str(e)}")
        return False


def get_traffic_statistics(stream_handlers):
    """Get comprehensive traffic statistics from all monitoring locations."""
    try:
        stats = {
            'total_locations': len(NODE_COORDINATES),
            'active_locations': 0,
            'total_vehicles': 0,
            'status_counts': {'lancar': 0, 'padat': 0, 'macet': 0},
            'location_details': []
        }
        
        for node_id, coordinates in NODE_COORDINATES.items():
            location_data = {
                'node_id': node_id,
                'name': coordinates['name'],
                'lat': coordinates['lat'],
                'lon': coordinates['lon'],
                'vehicle_count': 0,
                'status': 'unknown',
                'active': False
            }
            
            if node_id in stream_handlers:
                handler = stream_handlers[node_id]
                location_data['vehicle_count'] = handler.get_vehicle_count()
                location_data['status'] = handler.get_traffic_status()
                location_data['active'] = True
                
                stats['active_locations'] += 1
                stats['total_vehicles'] += location_data['vehicle_count']
                
                if location_data['status'] in stats['status_counts']:
                    stats['status_counts'][location_data['status']] += 1
            
            stats['location_details'].append(location_data)
        
        if stats['active_locations'] > 0:
            for status in stats['status_counts']:
                percentage = (stats['status_counts'][status] / stats['active_locations']) * 100
                stats['status_counts'][f'{status}_percentage'] = round(percentage, 1)
            stats['avg_vehicles_per_location'] = round(stats['total_vehicles'] / stats['active_locations'], 1)
        else:
            stats['avg_vehicles_per_location'] = 0
            
        return stats
        
    except Exception as e:
        logger.error(f"Error calculating traffic statistics: {str(e)}")
        return {'error': str(e), 'total_locations': 0, 'active_locations': 0, 'total_vehicles': 0}


def validate_coordinates():
    """Validate node coordinates."""
    validation_results = {'valid': True, 'issues': [], 'node_count': len(NODE_COORDINATES)}
    
    SEMARANG_BOUNDS = {'lat_min': -7.1, 'lat_max': -6.9, 'lon_min': 110.3, 'lon_max': 110.5}
    
    for node_id, coord in NODE_COORDINATES.items():
        if not (SEMARANG_BOUNDS['lat_min'] <= coord['lat'] <= SEMARANG_BOUNDS['lat_max']):
            validation_results['valid'] = False
            validation_results['issues'].append(f"Node {node_id} latitude out of bounds")
            
        if not (SEMARANG_BOUNDS['lon_min'] <= coord['lon'] <= SEMARANG_BOUNDS['lon_max']):
            validation_results['valid'] = False
            validation_results['issues'].append(f"Node {node_id} longitude out of bounds")
    
    return validation_results


_validation = validate_coordinates()
if not _validation['valid']:
    logger.warning(f"Coordinate validation issues: {_validation['issues']}")
else:
    logger.info(f"All {_validation['node_count']} coordinates validated successfully")