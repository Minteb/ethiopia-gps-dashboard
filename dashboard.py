import pandas as pd
import geopandas as gpd
import folium
from folium import plugins
from branca.element import MacroElement
from jinja2 import Template
import plotly.express as px
from dash import Dash, dcc, html, Input, Output, callback, dash_table
import dash_bootstrap_components as dbc

# ---------------------------
# 1. LOAD AND PREPARE GPS DATA
# ---------------------------
file_path = "Maize_Fingerprint_2015_EC_GPS_onlyUpdated.csv"
df = pd.read_csv(file_path)

# Standardise column names
df.rename(columns={
    'Region': 'region',
    'Zone': 'zone',
    'Woreda': 'woreda',
    'Kebele': 'kebele',
    'latitude': 'lat',
    'longitude': 'lon'
}, inplace=True)

# Remove rows with zero/invalid coordinates
df = df[(df['lat'] != 0) & (df['lon'] != 0)]

print(f"Total valid GPS points: {len(df)}")

# Unique regions for dropdown
regions = sorted(df['region'].dropna().unique())

# ---------------------------
# 2. LOAD AND CLEAN SHAPEFILE
# ---------------------------
shp_path = "eth_admin1.shp"
regions_gdf = gpd.read_file(shp_path)

if regions_gdf.crs != 'EPSG:4326':
    regions_gdf = regions_gdf.to_crs('EPSG:4326')

region_col = 'adm1_name'   # adjust if needed
if region_col not in regions_gdf.columns:
    raise KeyError(f"Column '{region_col}' not found. Available: {regions_gdf.columns.tolist()}")

regions_gdf_clean = regions_gdf[['geometry', region_col]].copy()

# ---------------------------
# 3. CUSTOM HOME BUTTON
# ---------------------------
class HomeButton(MacroElement):
    def __init__(self, position='topleft', home_coords=[9.0, 38.5], home_zoom=6):
        super().__init__()
        self._name = 'HomeButton'
        self.position = position
        self.home_coords = home_coords
        self.home_zoom = home_zoom
        self._template = Template("""
            {% macro script(this, kwargs) %}
                L.easyButton('fa-home', function(){
                    map.setView({{ this.home_coords }}, {{ this.home_zoom }});
                }).addTo({{ this._parent.get_name() }});
            {% endmacro %}
        """)

# ---------------------------
# 4. FUNCTION TO GENERATE MAP
# ---------------------------
def generate_map(selected_region=None, selected_zone=None, selected_woreda=None):
    m = folium.Map(location=[9.0, 38.5], zoom_start=6, control_scale=True, tiles=None)

    # Basemaps
    folium.TileLayer('openstreetmap', name='OpenStreetMap').add_to(m)
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satellite'
    ).add_to(m)

    # Region boundaries
    folium.GeoJson(
        regions_gdf_clean,
        name='Region Boundaries',
        style_function=lambda x: {
            'fillColor': 'transparent',
            'color': 'black',
            'weight': 1,
            'dashArray': '5, 5'
        },
        tooltip=folium.GeoJsonTooltip(fields=[region_col], aliases=['Region:'])
    ).add_to(m)

    # Filter points
    filtered = df.copy()
    if selected_region and selected_region != 'All':
        filtered = filtered[filtered['region'] == selected_region]
    if selected_zone and selected_zone != 'All':
        filtered = filtered[filtered['zone'] == selected_zone]
    if selected_woreda and selected_woreda != 'All':
        filtered = filtered[filtered['woreda'] == selected_woreda]

    print(f"Map: {len(filtered)} points after filtering")

    # GPS points layer
    point_group = folium.FeatureGroup(name='GPS Points')
    for _, row in filtered.iterrows():
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=4,
            color='red',
            fill=True,
            fillColor='red',
            fillOpacity=0.8,
            popup=(
                f"<b>Region:</b> {row['region']}<br>"
                f"<b>Zone:</b> {row['zone']}<br>"
                f"<b>Woreda:</b> {row['woreda']}<br>"
                f"<b>Kebele:</b> {row['kebele']}"
            )
        ).add_to(point_group)
    point_group.add_to(m)

    # Layer control, fullscreen, home button
    folium.LayerControl().add_to(m)
    plugins.Fullscreen().add_to(m)
    HomeButton().add_to(m)

    return m._repr_html_()

# ---------------------------
# 5. DASH APP
# ---------------------------
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = dbc.Container([
    html.H1("Ethiopia GPS Points Dashboard", className="text-center mt-4 mb-4"),

    dbc.Row([
        dbc.Col([
            html.Label("Select Region"),
            dcc.Dropdown(
                id='region-dropdown',
                options=[{'label': 'All', 'value': 'All'}] + [{'label': r, 'value': r} for r in regions],
                value='All',
                clearable=False
            )
        ], width=4),
        dbc.Col([
            html.Label("Select Zone"),
            dcc.Dropdown(id='zone-dropdown', options=[], value='All', clearable=False)
        ], width=4),
        dbc.Col([
            html.Label("Select Woreda"),
            dcc.Dropdown(id='woreda-dropdown', options=[], value='All', clearable=False)
        ], width=4),
    ], className="mb-4"),

    # Statistics cards and tables
    dbc.Row([
        dbc.Col([
            dbc.Card(
                dbc.CardBody([
                    html.H5("Total GPS Points", className="card-title"),
                    html.H2(id='total-points', children="0", className="card-text text-primary")
                ]),
                color="light",
                inverse=False,
                className="text-center"
            )
        ], width=6),
        dbc.Col([
            dbc.Card(
                dbc.CardBody([
                    html.H5("Points per Region", className="card-title"),
                    dash_table.DataTable(
                        id='region-table',
                        columns=[{"name": "Region", "id": "region"}, {"name": "Count", "id": "count"}],
                        style_table={'overflowX': 'auto'},
                        style_cell={'textAlign': 'left', 'padding': '5px'},
                        style_header={'fontWeight': 'bold'}
                    )
                ])
            )
        ], width=6),
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            dcc.Graph(id='bar-chart')
        ], width=6),
        dbc.Col([
            dcc.Graph(id='pie-chart')
        ], width=6),
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            html.Iframe(id='map', width='100%', height='600')
        ], width=12)
    ]),

    # Footer with developer information
    html.Hr(),
    html.Footer(
        "Developed By: Mintesnot Berhanu, geospatial Data science expert and Minteb11@gmail.com",
        className="text-center text-muted"
    )
], fluid=True)

# ---------------------------
# 6. CALLBACKS
# ---------------------------
@callback(
    Output('zone-dropdown', 'options'),
    Output('zone-dropdown', 'value'),
    Input('region-dropdown', 'value')
)
def set_zone_options(selected_region):
    if selected_region == 'All':
        zones = ['All'] + sorted(df['zone'].dropna().unique())
    else:
        zones = ['All'] + sorted(df[df['region'] == selected_region]['zone'].dropna().unique())
    return [{'label': z, 'value': z} for z in zones], 'All'

@callback(
    Output('woreda-dropdown', 'options'),
    Output('woreda-dropdown', 'value'),
    Input('region-dropdown', 'value'),
    Input('zone-dropdown', 'value')
)
def set_woreda_options(selected_region, selected_zone):
    filtered = df.copy()
    if selected_region != 'All':
        filtered = filtered[filtered['region'] == selected_region]
    if selected_zone != 'All':
        filtered = filtered[filtered['zone'] == selected_zone]
    woredas = ['All'] + sorted(filtered['woreda'].dropna().unique())
    return [{'label': w, 'value': w} for w in woredas], 'All'

@callback(
    Output('total-points', 'children'),
    Output('region-table', 'data'),
    Output('bar-chart', 'figure'),
    Output('pie-chart', 'figure'),
    Input('region-dropdown', 'value'),
    Input('zone-dropdown', 'value'),
    Input('woreda-dropdown', 'value')
)
def update_stats_and_graphs(selected_region, selected_zone, selected_woreda):
    filtered = df.copy()
    if selected_region != 'All':
        filtered = filtered[filtered['region'] == selected_region]
    if selected_zone != 'All':
        filtered = filtered[filtered['zone'] == selected_zone]
    if selected_woreda != 'All':
        filtered = filtered[filtered['woreda'] == selected_woreda]

    # Total points
    total = len(filtered)

    # Region counts
    region_counts = filtered['region'].value_counts().reset_index()
    region_counts.columns = ['region', 'count']
    region_data = region_counts.to_dict('records')

    # Bar chart
    if selected_woreda == 'All':
        bar_data = filtered['woreda'].value_counts().reset_index()
        bar_data.columns = ['woreda', 'count']
        bar_fig = px.bar(bar_data, x='woreda', y='count', title='Points per Woreda')
    else:
        bar_data = filtered['kebele'].value_counts().reset_index()
        bar_data.columns = ['kebele', 'count']
        bar_fig = px.bar(bar_data, x='kebele', y='count', title='Points per Kebele')

    # Pie chart
    if selected_zone == 'All':
        pie_data = filtered['zone'].value_counts().reset_index()
        pie_data.columns = ['zone', 'count']
        pie_fig = px.pie(pie_data, values='count', names='zone', title='Distribution by Zone')
    else:
        pie_data = filtered['kebele'].value_counts().reset_index()
        pie_data.columns = ['kebele', 'count']
        pie_fig = px.pie(pie_data, values='count', names='kebele', title='Distribution by Kebele')

    return total, region_data, bar_fig, pie_fig

@callback(
    Output('map', 'srcDoc'),
    Input('region-dropdown', 'value'),
    Input('zone-dropdown', 'value'),
    Input('woreda-dropdown', 'value')
)
def update_map(selected_region, selected_zone, selected_woreda):
    try:
        return generate_map(selected_region, selected_zone, selected_woreda)
    except Exception as e:
        print("❌ Map error:", e)
        import traceback
        traceback.print_exc()
        m = folium.Map(location=[9.0, 38.5], zoom_start=6)
        folium.Marker([9.0, 38.5], popup=f"Error: {e}", icon=folium.Icon(color='red')).add_to(m)
        return m._repr_html_()

# ---------------------------
# 7. RUN
# ---------------------------
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8050)
# Add this line at the bottom of dashboard.py
wsgi_app = app.server