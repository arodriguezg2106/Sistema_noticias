import shapefile
from pathlib import Path

shp_path = Path(r"D:\arodriguezg\Downloads\dest25gw\dest25gw.shp")
sf = shapefile.Reader(str(shp_path))
xmin, ymin, xmax, ymax = sf.bbox
width, height = 1000, 680
padding = 30

def map_x(x):
    return padding + (x - xmin) / (xmax - xmin) * (width - 2 * padding)

def map_y(y):
    return height - (padding + (y - ymin) / (ymax - ymin) * (height - 2 * padding))

gov_eeuu = {'Baja California', 'Chihuahua', 'Michoacán de Ocampo', 'Quintana Roo', 'Sinaloa', 'Sonora'}
renov_gov = {'Nuevo León', 'Zacatecas', 'Guerrero', 'Campeche', 'Tabasco', 'San Luis Potosí', 'Nayarit', 'Baja California Sur', 'Querétaro', 'Morelos'}
renov_congreso = {'Jalisco', 'Coahuila de Zaragoza', 'Durango', 'Tamaulipas', 'Hidalgo', 'México', 'Ciudad de México', 'Puebla', 'Veracruz de Ignacio de la Llave', 'Oaxaca', 'Chiapas', 'Yucatán'}

name_map = {
    'Coahuila de Zaragoza': 'Coahuila',
    'Michoacán de Ocampo': 'Michoacán',
    'México': 'Estado de México',
    'Ciudad de México': 'Ciudad de México',
    'Veracruz de Ignacio de la Llave': 'Veracruz',
}

svg_paths = []
for shape_rec in sf.shapeRecords():
    raw_name = shape_rec.record['NOMGEO']
    clean_name = name_map.get(raw_name, raw_name)
    
    if raw_name in gov_eeuu:
        cat_class = 'gov-eeuu'
    elif raw_name in renov_gov:
        cat_class = 'renov-gov'
    elif raw_name in renov_congreso:
        cat_class = 'renov-congreso'
    else:
        cat_class = 'sin-cambios'
        
    shape = shape_rec.shape
    points = shape.points
    parts = list(shape.parts) + [len(points)]
    
    d_parts = []
    for i in range(len(parts) - 1):
        sub_points = points[parts[i]:parts[i+1]]
        if not sub_points or len(sub_points) < 3:
            continue
        
        # Decimate points (every 10th point) for super fast rendering & small file size while preserving high detail
        step = 10 if len(sub_points) > 100 else 2
        sub_points_dec = sub_points[::step]
        if sub_points_dec[-1] != sub_points[-1]:
            sub_points_dec.append(sub_points[-1])
            
        cmds = []
        for idx, (px, py) in enumerate(sub_points_dec):
            sx = round(map_x(px), 1)
            sy = round(map_y(py), 1)
            if idx == 0:
                cmds.append(f'M {sx} {sy}')
            else:
                cmds.append(f'L {sx} {sy}')
        cmds.append('Z')
        d_parts.append(' '.join(cmds))
        
    d_attr = ' '.join(d_parts)
    state_id = f"path-{clean_name.replace(' ', '_')}"
    path_elem = f'<path id="{state_id}" class="state-path {cat_class}" data-state="{clean_name}" d="{d_attr}" onclick="openStateView(\'{clean_name}\')" />'
    svg_paths.append(path_elem)

out_file = Path('data/shp_svg_paths.html')
out_file.parent.mkdir(parents=True, exist_ok=True)
out_file.write_text('\n'.join(svg_paths), encoding='utf-8')
print(f'Successfully generated lightweight SVG state paths! Size: {out_file.stat().st_size / 1024:.1f} KB')
