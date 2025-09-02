import csv
import os
from datetime import datetime, timezone, timedelta

def parse_csv(filepath):
    energy_data = []
    timestamps = []
    rows = []
    with open(filepath, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            rows.append(row)
            try:
                timestamp = int(row['start_time']) / 1000
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                tz_offset = timedelta(hours=2)
                local_dt = dt + tz_offset
                tz_diff = f"GMT{'+' if tz_offset.total_seconds() >= 0 else '-'}{abs(tz_offset.total_seconds()) // 3600:.0f}"
                timestamps.append(local_dt.strftime(f'%Y-%m-%d %H:%M:%S ({tz_diff})'))
                energy_value = float(row['Energy (J)'])
                energy_data.append(energy_value)
            except (ValueError, KeyError):
                continue
    return timestamps, energy_data, rows

def reduce_data(timestamps, energy_data, percentage):
    num_points = max(1, int(len(timestamps) * (percentage / 100)))
    step = len(timestamps) / num_points
    reduced_timestamps = []
    reduced_energy = []
    for i in range(num_points):
        start_idx = int(i * step)
        end_idx = int((i + 1) * step)
        chunk = slice(start_idx, min(end_idx, len(timestamps)))
        reduced_timestamps.append(timestamps[chunk.start])
        valid_energy = [e for e in energy_data[chunk] if e >= 0]
        if valid_energy:
            reduced_energy.append(sum(valid_energy) / len(valid_energy))
        else:
            reduced_energy.append(0)
    return reduced_timestamps, reduced_energy

def generate_html(timestamps, energy_data, rows):
    table_headers = rows[0].keys()
    table_rows = ''.join(
        f'''<tr>{''.join(f'<td>{str(cell).replace(chr(10), " ").replace(chr(13), " ")}</td>' for cell in row.values())}</tr>''' for row in rows
    )
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Energy Chart</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            .chart-container {{
                width: 80%;
                margin: 20px auto;
            }}
            .controls {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                width: 80%;
                margin: 20px auto;
            }}
            .table-container {{
                width: 80%;
                margin: 20px auto;
                max-height: 300px;
                overflow-y: auto;
                border: 1px solid #ddd;
                background-color: #fff;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
                white-space: nowrap;
            }}
            th {{
                background-color: #f2f2f2;
                position: sticky;
                top: 0;
            }}
            tr:nth-child(even) {{
                background-color: #f9f9f9;
            }}
        </style>
    </head>
    <body>
        <h1 style="text-align: center;">Energy Chart</h1>
        <div class="chart-container">
            <canvas id="energyChart"></canvas>
        </div>
        <div class="controls">
            <div id="percentageControl">
                <label for="percentagePoints">Percentage of Graph Points:</label>
                <input type="number" id="percentagePoints" value="100" min="10" max="100" step="10">
                <button onclick="updateChart()">Update</button>
            </div>
            <div>
                <label for="searchApp">Search:</label>
                <input type="text" id="searchApp" placeholder="Search in table">
                <button onclick="searchTable()">Search</button>
            </div>
            <div>
                <label for="sortOrder">Sort Energy:</label>
                <select id="sortOrder" onchange="sortTable()">
                    <option value="asc">Ascending</option>
                    <option value="desc">Descending</option>
                </select>
            </div>
            <div>
                <label for="chartView">Select View:</label>
                <select id="chartView" onchange="updateChartView()">
                    <option value="energy">Energy (J)</option>
                    <option value="cumulativeEnergy">Cumulative Energy (J)</option>
                </select>
            </div>
        </div>
        <div class="table-container">
            <table id="dataTable">
                <thead>
                    <tr>{''.join(f'<th>{header}</th>' for header in table_headers)}</tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
        <script>
            let originalData = {{
                timestamps: {timestamps},
                energy: {energy_data}
            }};

            const createChart = (ctxId, label, data, xLabel, yLabel) => {{
                const ctx = document.getElementById(ctxId).getContext('2d');
                return new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: data.timestamps,
                        datasets: [{{
                            label: label,
                            data: data.values,
                            borderColor: 'rgba(75, 192, 192, 1)',
                            backgroundColor: 'rgba(75, 192, 192, 0.2)',
                            borderWidth: 2
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        plugins: {{
                            legend: {{
                                position: 'top',
                            }}
                        }},
                        scales: {{
                            x: {{
                                title: {{
                                    display: true,
                                    text: xLabel
                                }}
                            }},
                            y: {{
                                title: {{
                                    display: true,
                                    text: yLabel
                                }}
                            }}
                        }}
                    }}
                }});
            }};

            let energyChart = createChart('energyChart', 'Energy (J)', {{ timestamps: originalData.timestamps, values: originalData.energy }}, 'Converted Timestamp', 'Energy (J)');

            const updateChart = () => {{
                const percentage = parseInt(document.getElementById('percentagePoints').value);
                const reducedData = reduceData(originalData.timestamps, originalData.energy, percentage);
                energyChart.data.labels = reducedData.timestamps;
                energyChart.data.datasets[0].data = reducedData.energy;
                energyChart.update();
            }};

            const reduceData = (timestamps, energy, percentage) => {{
                const numPoints = Math.max(1, Math.floor((percentage / 100) * timestamps.length));
                const step = timestamps.length / numPoints;
                const reducedTimestamps = [];
                const reducedEnergy = [];
                for (let i = 0; i < numPoints; i++) {{
                    const startIdx = Math.floor(i * step);
                    const endIdx = Math.floor((i + 1) * step);
                    const chunk = energy.slice(startIdx, endIdx);
                    reducedTimestamps.push(timestamps[startIdx]);
                    const validChunk = chunk.filter(e => e >= 0);
                    if (validChunk.length > 0) {{
                        reducedEnergy.push(validChunk.reduce((a, b) => a + b, 0) / validChunk.length);
                    }} else {{
                        reducedEnergy.push(0);
                    }}
                }}
                return {{ timestamps: reducedTimestamps, energy: reducedEnergy }};
            }};

            const calculateCumulativeEnergy = (energy) => {{
                const cumulative = [];
                energy.reduce((acc, value, index) => {{
                    cumulative[index] = acc + value;
                    return cumulative[index];
                }}, 0);
                return cumulative;
            }};

            const updateChartView = () => {{
                const selectedView = document.getElementById('chartView').value;
                let updatedData;

                if (selectedView === 'cumulativeEnergy') {{
                    updatedData = calculateCumulativeEnergy(originalData.energy);
                    document.getElementById('percentageControl').style.display = 'none';
                }} else {{
                    updatedData = originalData.energy;
                    document.getElementById('percentageControl').style.display = 'block';
                }}

                energyChart.data.datasets[0].data = updatedData;
                energyChart.update();
            }};

            const searchTable = () => {{
                const searchValue = document.getElementById('searchApp').value.toLowerCase();
                const rows = document.querySelectorAll('#dataTable tbody tr');
                rows.forEach(row => {{
                    const cells = Array.from(row.cells);
                    const matches = cells.some(cell => cell.textContent.toLowerCase().includes(searchValue));
                    row.style.display = matches ? '' : 'none';
                }});
            }};

            const sortTable = () => {{
                const table = document.getElementById('dataTable');
                const rows = Array.from(table.rows).slice(1); // Exclude header row
                const sortOrder = document.getElementById('sortOrder').value;
                const energyIndex = Array.from(table.rows[0].cells).findIndex(cell => cell.textContent === 'Energy (J)'); // Find the energy column index

                rows.sort((a, b) => {{
                    const energyA = parseFloat(a.cells[energyIndex].textContent) || 0;
                    const energyB = parseFloat(b.cells[energyIndex].textContent) || 0;
                    return sortOrder === 'asc' ? energyA - energyB : energyB - energyA;
                }});

                const tbody = table.querySelector('tbody');
                rows.forEach(row => tbody.appendChild(row));
            }};
        </script>
    </body>
    </html>
    """
    return html_content

def process_html_file(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    timestamps, energy_data, rows = parse_csv(file_path)
    return generate_html(timestamps, energy_data, rows)
