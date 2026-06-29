#!/usr/bin/env python3
import http.server
import socketserver
import webbrowser
import threading
import math

# this string holds the whole simulation webpage
# a python server to host it so it opens in the browser automatically
html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>harvest sync project</title>
    <style>
        /* green forharvestor and tractor blue colors */
        body { font-family: sans-serif; background: #222; color: #fff; padding: 20px; }
        .container { display: flex; gap: 20px; justify-content: center; }
        canvas { background: #111; border: 2px solid #555; border-radius: 8px; }
        .panel { background: #333; padding: 15px; border-radius: 8px; width: 320px; }
        
        /* stats box for all the live sensor data */
        .stats { 
            background: #444; padding: 10px; margin-bottom: 10px; 
            font-family: monospace; border-left: 4px solid #46C7D6; 
        }
        
        /* e-stop button turns yellow when clicked to show it is active */
        .stop-btn { width: 100%; padding: 15px; background: #c00; color: #fff; font-weight: bold; cursor: pointer; border: none; }
        .stop-active { background: #ffea00; color: #000; }
        
        label { display: block; margin-top: 15px; font-size: 11px; color: #aaa; }
        input[type=range] { width: 100%; }
        .val { color: #46C7D6; float: right; font-weight: bold; }
        .full { color: #ff3300; font-weight: bold; }
    </style>
</head>
<body>

    <h2 style="text-align:center;">harvester sync and fill sim</h2>
    
    <div class="container">
        <!-- this is where the machines are drawn -->
        <canvas id="field" width="600" height="550"></canvas>

        <div class="panel">
            <button id="estop" class="stop-btn">EMERGENCY STOP</button>
            
            <label>harvester speed (km/h)</label>
            <input type="range" id="hSpeedSlider" min="0" max="14" step="0.5" value="8">

            <label>chute pivot speed (hydraulics)</label>
            <input type="range" id="pSpeedSlider" min="0.01" max="0.3" step="0.01" value="0.08">
            
            <hr style="border: 0; border-top: 1px solid #444; margin: 20px 0;">
            
            <div class="stats">
                <div>harvester: <span class="val"><span id="hSpd">0.0</span> km/h</span></div>
                <div>tractor:   <span class="val"><span id="tSpd">0.0</span> km/h</span></div>
                <div style="color:#fff">sync error: <span class="val"><span id="dist">0.0</span> m</span></div>
                <div>chute to cab: <span class="val"><span id="relDist">0.0</span> m</span></div>
                <div style="color:#fff">chute angle: <span class="val"><span id="chDeg">0</span>&deg;</span></div>
                
                <hr style="border-color:#555">
                <!-- quantity is calculated as (pct/100) * 40m3 -->
                <div style="color:#fff">fill quantity: <span class="val"><span id="vol">0.0</span> m&sup3;</span></div>
                <div style="color:#fff">fill level: <span class="val" id="fillBox"><span id="fill">0</span>%</span></div>
            </div>

            <button id="resetBtn">reset trailer</button>
            <button id="bumpBtn">bump tractor back</button>
        </div>
    </div>

<script>
    const canvas = document.getElementById('field');
    const ctx = canvas.getContext('2d');

    // simulation variables
    let hSpeed = 8.0, hTarget = 8.0, tSpeed = 0.0;
    let gap = 4.0; // distance error in meters
    let moveSpeed = 0.08; // speed of the chute body pivot
    let stopped = false;
    
    // trailer is an 18-cell array (3 columns x 6 rows)
    let grid = new Array(18).fill(0); 
    let particles = [];
    let angle = 0; // chute angle in radians
    const length = 85; // length of chute arm in pixels
    const max_volume = 40.0; // standard tractor trailer capacity

    // handle UI inputs
    document.getElementById('hSpeedSlider').oninput = (e) => hTarget = parseFloat(e.target.value);
    document.getElementById('pSpeedSlider').oninput = (e) => moveSpeed = parseFloat(e.target.value);
    document.getElementById('resetBtn').onclick = () => {
        grid.fill(0);
        document.getElementById('fillBox').classList.remove('full');
    };
    document.getElementById('bumpBtn').onclick = () => gap += 3.5; 
    
    // e-stop forces speeds to 0 and stops the loop
    document.getElementById('estop').onclick = function() {
        stopped = !stopped;
        this.classList.toggle('stop-active', stopped);
        this.innerText = stopped ? "RESET SYSTEM" : "EMERGENCY STOP";
    };

    // physics loop runs 60 times a second
    function loop(dt) {
        if (stopped) { hSpeed = 0; tSpeed = 0; return; }

        // harvester moves to target speed
        hSpeed += (hTarget - hSpeed) * 0.05;

        // command speed = harvester speed - (gap * gain)
        // i used a gain of 2.0 to keep it stable but responsive
        tSpeed = hSpeed - (gap * 2.0);
        if (tSpeed < 0) tSpeed = 0;

        // convert kmh to meters per second using 3.6 factor
        // then add speed difference to the gap error
        let delta = (tSpeed - hSpeed) / 3.6;
        gap += delta * dt;

        // find the emptiest of the 18 zones to aim the chute
        let low = grid.indexOf(Math.min(...grid));
        let row = Math.floor(low / 3);
        
        // move chute angle toward that row (pivoting logic)
        let targetAngle = (row - 2.5) * 0.25; 
        angle += (targetAngle - angle) * moveSpeed;

        // trig to find the tip of the chute (axis + offset)
        // axis is fixed at 300, 210 on the harvester 
        let tx = 300 + length * math_cos(angle);
        let ty = 210 + length * math_sin(angle);
        
        // tractor cab position on screen (405 is x distance)
        let cx = 405, cy = (170 + (gap * 20)) - 20;
        
        // pythagoras to find distance from chute tip to driver
        let dx = tx - cx; 
        let dy = ty - cy;
        let meters = Math.sqrt(dx*dx + dy*dy) / 20; // 20 pixels = 1 meter
        
        document.getElementById('relDist').innerText = meters.toFixed(1);
        document.getElementById('chDeg').innerText = (angle * (180/Math.PI)).toFixed(0);

        // calculation for total fill (average of the 18 spots)
        let currentFill = (grid.reduce((a, b) => a + b, 0) / 18 * 100);
        let isFull = currentFill >= 99.9;

        // only drop grain if synced, harvester moving, and not full
        if (Math.abs(gap) < 1.0 && hSpeed > 0.5 && !isFull) {
            grid[low] += 0.005; // add volume to the lowest zone
            if (Math.random() > 0.6) {
                // Lagrangian particles for the grain stream visual
                particles.push({tipX: tx, tipY: ty, tarX: 400, tarY: 170 + (gap*20) + (row*15), life: 0});
            }
        } else if (isFull) {
            document.getElementById('fillBox').classList.add('full');
        }

        particles.forEach(p => p.life += 0.03);
        particles = particles.filter(p => p.life < 1);
    }

    // math for the trig
    function math_cos(a) { return Math.cos(a); }
    function math_sin(a) { return Math.sin(a); }

    function draw() {
        ctx.clearRect(0, 0, 600, 550);

        // draw harvester body (green)
        ctx.fillStyle = "#2e7d32";
        ctx.fillRect(280, 170, 40, 80);
        ctx.fillStyle = "white";
        ctx.beginPath(); ctx.arc(300, 210, 4, 0, 7); ctx.fill(); // the axis bolt
        
        // draw chute arm (white rigid body)
        ctx.strokeStyle = "#bbb";
        ctx.lineWidth = 6;
        ctx.beginPath();
        ctx.moveTo(300, 210);
        let chuteX = 300 + length * Math.cos(angle);
        let chuteY = 210 + Math.sin(angle) * length;
        ctx.lineTo(chuteX, chuteY);
        ctx.stroke();

        // draw tractor and trailer (blue/gray)
        let yPos = 170 + (gap * 20); 
        ctx.fillStyle = "#444";
        ctx.fillRect(380, yPos, 50, 100); // the trailer
        ctx.fillStyle = "#1565c0";
        ctx.fillRect(385, yPos - 40, 40, 40); // the tractor cab

        // draw dashed line for sensor vector
        ctx.save();
        ctx.setLineDash([5, 5]); 
        ctx.strokeStyle = "#46C7D6";
        ctx.beginPath();
        ctx.moveTo(chuteX, chuteY); 
        ctx.lineTo(405, yPos - 20); 
        ctx.stroke();
        ctx.restore();

        // display distance and angle on the sensor line
        let txt = document.getElementById('relDist').innerText + "m @ " + document.getElementById('chDeg').innerText + "deg";
        ctx.fillStyle = "#46C7D6";
        ctx.font = "bold 11px monospace";
        ctx.fillText(txt, (chuteX + 405)/2 + 10, (chuteY + yPos - 20)/2);

        // draw the grain volume in the 18 zones
        for(let i=0; i<18; i++) {
            if(grid[i] > 0) {
                ctx.fillStyle = `rgba(255, 215, 0, ${grid[i]})`;
                ctx.fillRect(385 + (i%3 * 14), yPos + 5 + (Math.floor(i/3)*15), 12, 12);
            }
        }

        // draw the particles flying from chute tip to trailer target
        ctx.fillStyle = "gold";
        particles.forEach(p => {
            let px = p.tipX + (p.tarX - p.tipX) * p.life;
            let py = p.tipY + (p.tarY - p.tipY) * p.life - Math.sin(p.life * Math.PI) * 15;
            ctx.fillRect(px, py, 3, 3);
        });

        // update the ui text readouts
        document.getElementById('hSpd').innerText = hSpeed.toFixed(1);
        document.getElementById('tSpd').innerText = tSpeed.toFixed(1);
        document.getElementById('dist').innerText = gap.toFixed(2);
        
        let pct = (grid.reduce((a, b) => a + b, 0) / 18 * 100);
        document.getElementById('fill').innerText = pct >= 100 ? "100" : pct.toFixed(0);
        
        let currentVol = (pct / 100) * max_volume;
        document.getElementById('vol').innerText = currentVol.toFixed(1);
    }

    function start() {
        loop(0.016); 
        draw();
        requestAnimationFrame(start);
    }
    start();
</script>
</body>
</html>
"""

# python backend serves the string to localhost
class Server(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(html_content.encode())

def run():
    port = 8080
    s = socketserver.TCPServer(("", port), Server)
    # open the browser after a 1 second delay
    threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    try:
        print(f"sim running at http://localhost:{port}")
        s.serve_forever()
    except KeyboardInterrupt:
        s.shutdown()

if __name__ == "__main__":
    run()
