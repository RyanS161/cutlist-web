#!/usr/bin/env python3
"""
Design Review Tool - A web-based interface for collecting human feedback on generated designs.
Run with: python collect_results.py <experiment_outputs_path>
"""

import os
import sys
import json
import csv
import random
import base64
import time
import re
from pathlib import Path
from flask import (
    Flask,
    render_template_string,
    request,
    jsonify,
    send_from_directory,
    redirect,
    url_for,
)

try:
    import pandas as pd
    import matplotlib.pyplot as plt
    import numpy as np

    ANALYTICS_AVAILABLE = True
except ImportError:
    ANALYTICS_AVAILABLE = False

try:
    import google.generativeai as genai

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

app = Flask(__name__)

# Global state
EXPERIMENT_PATH = None
REVIEWER_NAME = None
DESIGNS = []
CURRENT_INDEX = 0
RATINGS = {}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Design Review Tool</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        html, body {
            height: 100%;
            overflow: hidden;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
        }
        .review-layout {
            display: grid;
            grid-template-columns: 1fr 1fr;
            grid-template-rows: auto 1fr auto;
            height: 100vh;
            padding: 10px;
            gap: 10px;
        }
        .header {
            grid-column: 1 / -1;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 15px;
            background: rgba(255,255,255,0.1);
            border-radius: 8px;
        }
        .progress {
            font-size: 1em;
            color: #4ade80;
        }
        .model-badge {
            background: #6366f1;
            padding: 6px 14px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9em;
        }
        .left-panel {
            display: flex;
            flex-direction: column;
            gap: 10px;
            overflow: hidden;
        }
        .prompt-box {
            background: rgba(255,255,255,0.1);
            padding: 12px 15px;
            border-radius: 8px;
            border-left: 4px solid #f59e0b;
        }
        .prompt-label {
            font-size: 0.75em;
            color: #94a3b8;
            margin-bottom: 4px;
            text-transform: uppercase;
        }
        .prompt-text {
            font-size: 1em;
            line-height: 1.4;
        }
        .media-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            flex: 1;
            min-height: 0;
        }
        .media-card {
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
        .media-card img {
            width: 100%;
            height: 100%;
            object-fit: contain;
            flex: 1;
            min-height: 0;
        }
        .media-label {
            padding: 6px;
            text-align: center;
            background: rgba(0,0,0,0.3);
            font-size: 0.75em;
            color: #94a3b8;
        }
        .right-panel {
            display: flex;
            flex-direction: column;
            gap: 10px;
            overflow: hidden;
        }
        .stl-viewer {
            flex: 1;
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            overflow: hidden;
            position: relative;
            min-height: 0;
        }
        .stl-viewer canvas {
            width: 100% !important;
            height: 100% !important;
        }
        .stl-label {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 6px;
            text-align: center;
            background: rgba(0,0,0,0.5);
            font-size: 0.75em;
            color: #94a3b8;
        }
        .rating-section {
            background: rgba(255,255,255,0.1);
            padding: 12px;
            border-radius: 8px;
        }
        .rating-group {
            margin-bottom: 10px;
        }
        .rating-group:last-child {
            margin-bottom: 0;
        }
        .rating-label {
            font-size: 0.9em;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .rating-label .hint {
            font-size: 0.75em;
            color: #94a3b8;
            font-weight: normal;
        }
        .rating-buttons {
            display: flex;
            gap: 8px;
        }
        .rating-btn {
            flex: 1;
            padding: 10px 12px;
            border: 2px solid rgba(255,255,255,0.2);
            background: rgba(255,255,255,0.05);
            color: #fff;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.85em;
            transition: all 0.2s;
        }
        .rating-btn:hover {
            background: rgba(255,255,255,0.15);
            border-color: rgba(255,255,255,0.4);
        }
        .rating-btn.selected {
            background: #6366f1;
            border-color: #6366f1;
        }
        .rating-btn.r1.selected { background: #ef4444; border-color: #ef4444; }
        .rating-btn.r2.selected { background: #f97316; border-color: #f97316; }
        .rating-btn.r3.selected { background: #f59e0b; border-color: #f59e0b; }
        .rating-btn.r4.selected { background: #84cc16; border-color: #84cc16; }
        .rating-btn.r5.selected { background: #22c55e; border-color: #22c55e; }
        .footer {
            grid-column: 1 / -1;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 15px;
        }
        .nav-btn {
            padding: 10px 30px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            font-weight: 600;
            transition: all 0.2s;
        }
        .nav-btn.prev {
            background: rgba(255,255,255,0.2);
            color: #fff;
        }
        .nav-btn.prev:hover {
            background: rgba(255,255,255,0.3);
        }
        .nav-btn.next {
            background: #22c55e;
            color: #fff;
        }
        .nav-btn.next:hover {
            background: #16a34a;
        }
        .nav-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .keyboard-hints {
            color: #64748b;
            font-size: 0.8em;
        }
        kbd {
            background: rgba(255,255,255,0.1);
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
            font-size: 0.9em;
        }
        .login-container {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .login-box {
            background: rgba(255,255,255,0.1);
            padding: 40px;
            border-radius: 16px;
            text-align: center;
            width: 100%;
            max-width: 400px;
        }
        .login-box h1 {
            margin-bottom: 30px;
        }
        .login-box input {
            width: 100%;
            padding: 15px;
            border: 2px solid rgba(255,255,255,0.2);
            background: rgba(255,255,255,0.05);
            color: #fff;
            border-radius: 10px;
            font-size: 1.1em;
            margin-bottom: 20px;
        }
        .login-box input:focus {
            outline: none;
            border-color: #6366f1;
        }
        .login-box button {
            width: 100%;
            padding: 15px;
            background: #6366f1;
            color: #fff;
            border: none;
            border-radius: 10px;
            font-size: 1.1em;
            cursor: pointer;
            font-weight: 600;
        }
        .login-box button:hover {
            background: #4f46e5;
        }
        .complete-container {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .complete-box {
            background: rgba(255,255,255,0.1);
            padding: 60px;
            border-radius: 16px;
            text-align: center;
        }
        .complete-box h1 {
            color: #22c55e;
            margin-bottom: 20px;
            font-size: 2.5em;
        }
        .status-saved {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #22c55e;
            color: #fff;
            padding: 10px 20px;
            border-radius: 6px;
            opacity: 0;
            transition: opacity 0.3s;
            font-size: 0.9em;
        }
        .status-saved.show {
            opacity: 1;
        }
        .test-dashboard {
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            padding: 10px 12px;
            flex-shrink: 0;
        }
        .test-dashboard-header {
            font-size: 0.75em;
            color: #94a3b8;
            text-transform: uppercase;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
        }
        .test-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }
        .test-chip {
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.75em;
            font-weight: 500;
            cursor: default;
        }
        .test-chip.passed  { background: rgba(34,197,94,0.15);  border: 1px solid #22c55e; color: #22c55e; }
        .test-chip.failed  { background: rgba(239,68,68,0.15);  border: 1px solid #ef4444; color: #ef4444; }
        .test-chip.skipped { background: rgba(100,116,139,0.2); border: 1px solid #64748b; color: #94a3b8; }
        .test-chip.error   { background: rgba(245,158,11,0.15); border: 1px solid #f59e0b; color: #f59e0b; }
    </style>
</head>
<body>
    {% if page == 'login' %}
    <div class="login-container">
        <div class="login-box">
            <h1>🎨 Design Review</h1>
            <p style="margin-bottom: 20px; color: #94a3b8;">Enter your name to begin reviewing</p>
            <form action="/start" method="POST">
                <input type="text" name="reviewer_name" placeholder="Your Name" required autofocus>
                <button type="submit">Start Reviewing</button>
            </form>
            <p style="margin-top: 20px; color: #64748b; font-size: 0.9em;">
                {{ total_designs }} designs to review
            </p>
        </div>
    </div>
    
    {% elif page == 'review' %}
    <div class="review-layout">
        <div class="header">
            <div class="prompt-box" style="flex: 1; margin: 0 20px; border-left: none; border-radius: 8px; padding: 8px 15px;">
                <div class="prompt-label">PROMPT</div>
                <div class="prompt-text">{{ design.prompt }}</div>
            </div>
            <div style="display:flex; flex-direction:column; align-items:flex-end; gap:2px; margin-left:15px;">
                <div class="progress">{{ scored_count }} / {{ total }} scored</div>
                <div style="font-size:0.85em; color:#94a3b8;">Design {{ current + 1 }} / {{ total }}</div>
            </div>
            <div style="margin-left: 15px;">{{ reviewer }}</div>
        </div>
        
        <div class="left-panel">
            <div class="media-row">
                <div class="media-card">
                    <img src="/media/{{ design.model_type }}/{{ design.exp_id }}/{{ design.last_iteration }}/assembly.gif" alt="Design Animation">
                    <div class="media-label">Animation (GIF)</div>
                </div>
                <div class="media-card">
                    <img src="/media/{{ design.model_type }}/{{ design.exp_id }}/{{ design.last_iteration }}/views.png" alt="Design Preview">
                    <div class="media-label">Preview (PNG)</div>
                </div>
            </div>
            
            <div class="rating-section">
                <div class="rating-group">
                    <div class="rating-label">
                        Assemblability
                        <span class="hint">(<kbd>1</kbd>–<kbd>5</kbd>)</span>
                    </div>
                    <div class="rating-buttons" data-category="assemblability">
                        <button class="rating-btn r1 {% if ratings.assemblability == 1 %}selected{% endif %}" data-value="1" onclick="setRating('assemblability', 1)">1 - Poor</button>
                        <button class="rating-btn r2 {% if ratings.assemblability == 2 %}selected{% endif %}" data-value="2" onclick="setRating('assemblability', 2)">2 - Fair</button>
                        <button class="rating-btn r3 {% if ratings.assemblability == 3 %}selected{% endif %}" data-value="3" onclick="setRating('assemblability', 3)">3 - Okay</button>
                        <button class="rating-btn r4 {% if ratings.assemblability == 4 %}selected{% endif %}" data-value="4" onclick="setRating('assemblability', 4)">4 - Good</button>
                        <button class="rating-btn r5 {% if ratings.assemblability == 5 %}selected{% endif %}" data-value="5" onclick="setRating('assemblability', 5)">5 - Great</button>
                    </div>
                </div>
                
                <div class="rating-group">
                    <div class="rating-label">
                        Prompt Satisfaction
                        <span class="hint">(<kbd>Q</kbd>–<kbd>T</kbd>)</span>
                    </div>
                    <div class="rating-buttons" data-category="prompt_satisfaction">
                        <button class="rating-btn r1 {% if ratings.prompt_satisfaction == 1 %}selected{% endif %}" data-value="1" onclick="setRating('prompt_satisfaction', 1)">1 - Poor</button>
                        <button class="rating-btn r2 {% if ratings.prompt_satisfaction == 2 %}selected{% endif %}" data-value="2" onclick="setRating('prompt_satisfaction', 2)">2 - Fair</button>
                        <button class="rating-btn r3 {% if ratings.prompt_satisfaction == 3 %}selected{% endif %}" data-value="3" onclick="setRating('prompt_satisfaction', 3)">3 - Okay</button>
                        <button class="rating-btn r4 {% if ratings.prompt_satisfaction == 4 %}selected{% endif %}" data-value="4" onclick="setRating('prompt_satisfaction', 4)">4 - Good</button>
                        <button class="rating-btn r5 {% if ratings.prompt_satisfaction == 5 %}selected{% endif %}" data-value="5" onclick="setRating('prompt_satisfaction', 5)">5 - Great</button>
                    </div>
                </div>
                
                <div class="rating-group">
                    <div class="rating-label">
                        Design Quality
                        <span class="hint">(<kbd>A</kbd>–<kbd>G</kbd>)</span>
                    </div>
                    <div class="rating-buttons" data-category="design_quality">
                        <button class="rating-btn r1 {% if ratings.design_quality == 1 %}selected{% endif %}" data-value="1" onclick="setRating('design_quality', 1)">1 - Poor</button>
                        <button class="rating-btn r2 {% if ratings.design_quality == 2 %}selected{% endif %}" data-value="2" onclick="setRating('design_quality', 2)">2 - Fair</button>
                        <button class="rating-btn r3 {% if ratings.design_quality == 3 %}selected{% endif %}" data-value="3" onclick="setRating('design_quality', 3)">3 - Okay</button>
                        <button class="rating-btn r4 {% if ratings.design_quality == 4 %}selected{% endif %}" data-value="4" onclick="setRating('design_quality', 4)">4 - Good</button>
                        <button class="rating-btn r5 {% if ratings.design_quality == 5 %}selected{% endif %}" data-value="5" onclick="setRating('design_quality', 5)">5 - Great</button>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="right-panel">
            <div class="stl-viewer" id="stlViewer">
                <div class="stl-label">3D Model (drag to rotate, scroll to zoom)</div>
            </div>
            {% if test_results %}
            <div class="test-dashboard">
                <div class="test-dashboard-header">
                    <span>Test Results</span>
                    <span>
                        {{ test_results.passed }} passed
                        &middot; {{ test_results.failed }} failed
                        {% if test_results.skipped %}&middot; {{ test_results.skipped }} skipped{% endif %}
                        {% if test_results.errors %}&middot; {{ test_results.errors }} error{% endif %}
                    </span>
                </div>
                <div class="test-chips">
                    {% for test in test_results.tests %}
                    <div class="test-chip {{ test.status }}" title="{{ test.message }}">{{ test.name }}</div>
                    {% endfor %}
                </div>
            </div>
            {% endif %}
        </div>
        
        <div class="footer">
            {% if prev_unscored is not none %}
            <button class="nav-btn prev" style="background:#6366f1;" onclick="window.location.href='/review/{{ prev_unscored }}'">★ Prev Unscored</button>
            {% endif %}
            <button class="nav-btn prev" onclick="navigate(-1)" {% if current == 0 %}disabled{% endif %}>← Previous</button>
            <div class="keyboard-hints">
                <kbd>←</kbd><kbd>→</kbd> Navigate
            </div>
            <button class="nav-btn next" onclick="navigate(1)">Next →</button>
            {% if next_unscored is not none %}
            <button class="nav-btn next" style="background:#6366f1;" onclick="window.location.href='/review/{{ next_unscored }}'">Next Unscored ★</button>
            {% endif %}
        </div>
    </div>
    
    <div class="status-saved" id="statusSaved">✓ Saved</div>
    
    <script>
        let currentRatings = {{ ratings | tojson }};
        let scene, camera, renderer, controls, mesh;
        
        function initSTLViewer() {
            const container = document.getElementById('stlViewer');
            const width = container.clientWidth;
            const height = container.clientHeight;
            
            // Scene
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x1a1a2e);
            
            // Camera
            camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
            camera.position.set(0, 0, 100);
            
            // Renderer
            renderer = new THREE.WebGLRenderer({ antialias: true });
            renderer.setSize(width, height);
            renderer.setPixelRatio(window.devicePixelRatio);
            container.insertBefore(renderer.domElement, container.firstChild);
            
            // Controls
            controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.1;
            controls.rotateSpeed = 0.8;
            
            // Lights
            const ambientLight = new THREE.AmbientLight(0x404040, 0.5);
            scene.add(ambientLight);
            
            const directionalLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
            directionalLight1.position.set(1, 1, 1);
            scene.add(directionalLight1);
            
            const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.5);
            directionalLight2.position.set(-1, -1, -1);
            scene.add(directionalLight2);
            
            // Load STL
            const loader = new THREE.STLLoader();
            loader.load('/media/{{ design.model_type }}/{{ design.exp_id }}/{{ design.last_iteration }}/assembly.stl', function(geometry) {
                const material = new THREE.MeshPhongMaterial({ 
                    color: 0x6366f1,
                    specular: 0x111111,
                    shininess: 100
                });
                mesh = new THREE.Mesh(geometry, material);
                
                // Center geometry
                geometry.computeBoundingBox();
                const center = new THREE.Vector3();
                geometry.boundingBox.getCenter(center);
                geometry.translate(-center.x, -center.y, -center.z);
                
                // Scale to fit
                const size = new THREE.Vector3();
                geometry.boundingBox.getSize(size);
                const maxDim = Math.max(size.x, size.y, size.z);
                const scale = 50 / maxDim;
                mesh.scale.set(scale, scale, scale);
                
                scene.add(mesh);
            });
            
            // Handle resize
            window.addEventListener('resize', onWindowResize);
            
            // Animation loop
            animate();
        }
        
        function onWindowResize() {
            const container = document.getElementById('stlViewer');
            const width = container.clientWidth;
            const height = container.clientHeight;
            
            camera.aspect = width / height;
            camera.updateProjectionMatrix();
            renderer.setSize(width, height);
        }
        
        function animate() {
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
        }
        
        // Initialize on load
        window.addEventListener('load', initSTLViewer);
        
        function setRating(category, value) {
            currentRatings[category] = value;
            
            // Update UI
            const buttons = document.querySelectorAll(`[data-category="${category}"] .rating-btn`);
            buttons.forEach(btn => {
                btn.classList.remove('selected');
                if (parseInt(btn.dataset.value) === value) {
                    btn.classList.add('selected');
                }
            });
            
            // Save to server
            fetch('/rate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    index: {{ current }},
                    category: category,
                    value: value
                })
            }).then(() => {
                showSaved();
            });
        }
        
        function showSaved() {
            const el = document.getElementById('statusSaved');
            el.classList.add('show');
            setTimeout(() => el.classList.remove('show'), 1500);
        }
        
        function navigate(direction) {
            window.location.href = '/review/' + ({{ current }} + direction);
        }
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Don't trigger if user is typing in an input
            if (e.target.tagName === 'INPUT') return;
            
            switch(e.key) {
                // Assemblability: 1–5
                case '1': setRating('assemblability', 1); break;
                case '2': setRating('assemblability', 2); break;
                case '3': setRating('assemblability', 3); break;
                case '4': setRating('assemblability', 4); break;
                case '5': setRating('assemblability', 5); break;

                // Prompt Satisfaction: Q, W, E, R, T
                case 'q': case 'Q': setRating('prompt_satisfaction', 1); break;
                case 'w': case 'W': setRating('prompt_satisfaction', 2); break;
                case 'e': case 'E': setRating('prompt_satisfaction', 3); break;
                case 'r': case 'R': setRating('prompt_satisfaction', 4); break;
                case 't': case 'T': setRating('prompt_satisfaction', 5); break;

                // Design Quality: A, S, D, F, G
                case 'a': case 'A': setRating('design_quality', 1); break;
                case 's': case 'S': setRating('design_quality', 2); break;
                case 'd': case 'D': setRating('design_quality', 3); break;
                case 'f': case 'F': setRating('design_quality', 4); break;
                case 'g': case 'G': setRating('design_quality', 5); break;

                // Navigation
                case 'ArrowLeft': if ({{ current }} > 0) navigate(-1); break;
                case 'ArrowRight': navigate(1); break;
            }
        });
    </script>
    
    {% elif page == 'complete' %}
    <div class="complete-container">
        <div class="complete-box">
            <h1>🎉 All Done!</h1>
            <p style="font-size: 1.2em; margin-bottom: 20px;">
                You've reviewed all {{ total }} designs.
            </p>
            <p style="color: #94a3b8;">
                Results saved to: {{ csv_file }}
            </p>
            <br>
            <a href="/" style="color: #6366f1;">Start a new session</a>
        </div>
    </div>
    {% endif %}
</body>
</html>
"""


def load_designs(experiment_path: str) -> list:
    """Load all designs from the experiment directory structure."""
    designs = []
    experiment_path = Path(experiment_path)

    for model_dir in sorted(experiment_path.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue

        model_type = model_dir.name

        for exp_dir in sorted(model_dir.iterdir()):
            if not exp_dir.is_dir() or exp_dir.name.startswith("."):
                continue

            exp_id = exp_dir.name

            # Find the last iteration directory (iteration_0, iteration_1, ...)
            iter_dirs = sorted(
                [d for d in exp_dir.iterdir() if d.is_dir() and d.name.startswith("iteration_")],
                key=lambda d: int(d.name.split("_")[1])
            )
            last_iteration = iter_dirs[-1].name if iter_dirs else None

            # Read prompt from carpenter session context (first user message)
            prompt = ""
            context_files = sorted(exp_dir.glob("carpenter_session_*_context.json"))
            if context_files:
                try:
                    with open(context_files[0], "r") as f:
                        context = json.load(f)
                    for msg in context:
                        if msg.get("author") == "user":
                            parts = msg.get("parts", [])
                            if parts:
                                prompt = parts[0].get("text", "")
                            break
                except Exception as e:
                    print(f"Warning: Could not read {context_files[0]}: {e}")

            # Read generation time from run_metrics.json
            generation_time = None
            metrics_file = exp_dir / "run_metrics.json"
            if metrics_file.exists():
                try:
                    with open(metrics_file, "r") as f:
                        metrics = json.load(f)
                    generation_time = metrics.get("elapsed_wall_time_s")
                except Exception as e:
                    print(f"Warning: Could not read {metrics_file}: {e}")

            designs.append(
                {
                    "model_type": model_type,
                    "exp_id": exp_id,
                    "prompt": prompt,
                    "generation_time": generation_time,
                    "last_iteration": last_iteration,
                    "path": str(exp_dir),
                }
            )

    return designs


def save_ratings_to_csv():
    """Save current ratings to CSV file."""
    global RATINGS, REVIEWER_NAME, DESIGNS, EXPERIMENT_PATH

    if not REVIEWER_NAME:
        return

    csv_filename = f"{REVIEWER_NAME}_ratings.csv"
    csv_path = Path(EXPERIMENT_PATH) / csv_filename

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "model_type",
                "experiment_name",
                "prompt",
                "assemblability",
                "prompt_satisfaction",
                "design_quality",
            ]
        )

        for i, design in enumerate(DESIGNS):
            if design["last_iteration"] is None:
                a, p, q = -1, -1, -1
            else:
                rating = RATINGS.get(i, {})
                a = rating.get("assemblability", "")
                p = rating.get("prompt_satisfaction", "")
                q = rating.get("design_quality", "")
            writer.writerow(
                [
                    design["model_type"],
                    design["exp_id"],
                    design["prompt"],
                    a, p, q,
                ]
            )

    return csv_path


# =============================================================================
# GEMINI LLM REVIEW FUNCTIONS
# =============================================================================

GEMINI_REVIEW_PROMPT = """Based on the prompt and the four-view image provided, please rate each of the following on a scale from 1 to 5:

ASSEMBLABILITY:
- 1: Multiple floating/intersecting parts; clearly not assembleable
- 2: Major issues that would prevent assembly without significant rework
- 3: Partially assembleable; many tweaks needed
- 4: Mostly assembleable with minor issues
- 5: Fully assembleable by a robot with no obvious issues

PROMPT SATISFACTION:
- 1: The design in no way satisfies the user's request
- 2: The design barely satisfies the request; major elements are missing
- 3: The design partially satisfies the request
- 4: The design mostly satisfies the request with minor gaps
- 5: The design fully satisfies the user's request

DESIGN QUALITY:
- 1: Completely unusable, ugly, or otherwise very low-quality
- 2: Poor quality; significant improvements needed
- 3: Acceptable; a few improvements would help
- 4: Good quality; looks useful and well-constructed
- 5: Excellent quality; reflects ideal characteristics for the prompt category

The user's prompt was:
"{prompt}"

Please respond with ONLY a JSON object in this exact format (no markdown, no explanation):
{{"assemblability": <1-5>, "prompt_satisfaction": <1-5>, "design_quality": <1-5>}}
"""


def load_image_as_base64(image_path: str) -> str:
    """Load an image file and return its base64 encoding."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_image_mime_type(image_path: str) -> str:
    """Get the MIME type for an image file."""
    ext = Path(image_path).suffix.lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mime_types.get(ext, "image/png")


def review_design_with_gemini(design: dict, model, log_file) -> dict:
    """Use Gemini to review a single design and return ratings."""
    design_path = Path(design["path"])
    png_path = design_path / design["last_iteration"] / "views.png"

    # Prepare images for Gemini (only PNG, not GIF)
    image_parts = []

    if png_path.exists():
        image_parts.append(
            {"mime_type": "image/png", "data": load_image_as_base64(str(png_path))}
        )

    if not image_parts:
        print(
            f"  Warning: No images found for {design['model_type']}/{design['exp_id']}"
        )
        return None

    # Create the prompt
    prompt_text = GEMINI_REVIEW_PROMPT.format(prompt=design["prompt"])

    # Build the content for Gemini
    content = [prompt_text] + image_parts

    try:
        response = model.generate_content(content)
        response_text = response.text.strip()

        # Debug log: write raw Gemini output to log file
        log_file.write(f"\n{'=' * 60}\n")
        log_file.write(f"Design: {design['model_type']}/{design['exp_id']}\n")
        log_file.write(f"Prompt: {design['prompt']}\n")
        log_file.write(f"Raw Gemini response:\n{response_text}\n")
        log_file.flush()

        # Try to parse the JSON response
        # Handle potential markdown code blocks
        if "```" in response_text:
            # Extract JSON from code block
            match = re.search(r"```(?:json)?\s*({.*?})\s*```", response_text, re.DOTALL)
            if match:
                response_text = match.group(1)

        ratings = json.loads(response_text)

        # Validate ratings are in range 1-5
        for key in ["assemblability", "prompt_satisfaction", "design_quality"]:
            if key not in ratings or ratings[key] not in [1, 2, 3, 4, 5]:
                print(f"  Warning: Invalid rating for {key}: {ratings.get(key)}")
                return None

        return ratings

    except json.JSONDecodeError as e:
        print(f"  Error parsing Gemini response: {e}")
        print(f"  Response was: {response_text[:200]}...")
        return None
    except Exception as e:
        print(f"  Error calling Gemini API: {e}")
        return None


def save_gemini_ratings_to_csv(designs: list, ratings: dict, experiment_path: str):
    """Save Gemini ratings to CSV file."""
    csv_filename = "gemini_ratings.csv"
    csv_path = Path(experiment_path) / csv_filename

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "model_type",
                "experiment_name",
                "prompt",
                "assemblability",
                "prompt_satisfaction",
                "design_quality",
            ]
        )

        for i, design in enumerate(designs):
            if design["last_iteration"] is None:
                a, p, q = -1, -1, -1
            else:
                rating = ratings.get(i, {})
                a = rating.get("assemblability", "")
                p = rating.get("prompt_satisfaction", "")
                q = rating.get("design_quality", "")
            writer.writerow(
                [
                    design["model_type"],
                    design["exp_id"],
                    design["prompt"],
                    a, p, q,
                ]
            )

    return csv_path


def run_gemini_review(experiment_path: str, api_key: str):
    """Run Gemini review on all designs in the experiment directory."""
    if not GEMINI_AVAILABLE:
        print("Error: google-generativeai package not installed.")
        print("Install with: pip install google-generativeai")
        sys.exit(1)

    # Configure Gemini
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-pro")

    # Load designs (not randomized for LLM review - we want deterministic order)
    print(f"Loading designs from: {experiment_path}")
    designs = load_designs(experiment_path)

    if not designs:
        print("Error: No designs found.")
        sys.exit(1)

    print(f"Found {len(designs)} designs to review")
    print("=" * 50)
    print("Starting Gemini Review")
    print("=" * 50 + "\n")

    ratings = {}

    # Check for existing progress
    csv_path = Path(experiment_path) / "gemini_ratings.csv"
    if csv_path.exists():
        print("Found existing gemini_ratings.csv, loading progress...")
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                for i, design in enumerate(designs):
                    if (
                        design["model_type"] == row["model_type"]
                        and design["exp_id"] == row["experiment_name"]
                    ):
                        if (
                            row["assemblability"]
                            and row["prompt_satisfaction"]
                            and row["design_quality"]
                        ):
                            ratings[i] = {
                                "assemblability": int(row["assemblability"]),
                                "prompt_satisfaction": int(row["prompt_satisfaction"]),
                                "design_quality": int(row["design_quality"]),
                            }
                        break
        print(f"Loaded {len(ratings)} existing ratings\\n")

    # Open log file for debug output
    log_path = Path(experiment_path) / "gemini_debug.log"
    print(f"Debug log: {log_path}")

    with open(log_path, "a") as log_file:
        log_file.write(f"\\n\\n{'#' * 60}\\n")
        log_file.write(
            f"# Gemini Review Session Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\\n"
        )
        log_file.write(f"{'#' * 60}\\n")

        for i, design in enumerate(designs):
            # Skip if already rated
            if i in ratings:
                print(
                    f"[{i + 1}/{len(designs)}] Skipping {design['model_type']}/{design['exp_id']} (already rated)"
                )
                continue

            print(
                f"[{i + 1}/{len(designs)}] Reviewing {design['model_type']}/{design['exp_id']}..."
            )

            result = review_design_with_gemini(design, model, log_file)

            if result:
                ratings[i] = result
                print(
                    f"  Ratings: A={result['assemblability']}, P={result['prompt_satisfaction']}, Q={result['design_quality']}"
                )
            else:
                print("  Failed to get ratings, skipping...")

            # Save progress after each review
            save_gemini_ratings_to_csv(designs, ratings, experiment_path)

            # Small delay to avoid rate limiting
            time.sleep(0.5)

    print("\\n" + "=" * 50)
    print(f"Review complete! Rated {len(ratings)}/{len(designs)} designs.")
    print(f"Results saved to: {csv_path}")
    print("=" * 50)


# =============================================================================
# FLASK WEB APP ROUTES
# =============================================================================


@app.route("/")
def index():
    """Show login page."""
    return render_template_string(
        HTML_TEMPLATE, page="login", total_designs=len(DESIGNS)
    )


@app.route("/start", methods=["POST"])
def start():
    """Start a review session."""
    global REVIEWER_NAME, RATINGS, CURRENT_INDEX

    REVIEWER_NAME = request.form.get("reviewer_name", "anonymous").strip()
    if not REVIEWER_NAME:
        REVIEWER_NAME = "anonymous"

    # Load existing ratings if CSV exists
    csv_filename = f"{REVIEWER_NAME}_ratings.csv"
    csv_path = Path(EXPERIMENT_PATH) / csv_filename

    if csv_path.exists():
        # Load previous ratings
        RATINGS = {}
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Find matching design index
                for i, design in enumerate(DESIGNS):
                    if (
                        design["model_type"] == row["model_type"]
                        and design["exp_id"] == row["experiment_name"]
                    ):
                        RATINGS[i] = {
                            "assemblability": int(row["assemblability"])
                            if row["assemblability"]
                            else None,
                            "prompt_satisfaction": int(row["prompt_satisfaction"])
                            if row["prompt_satisfaction"]
                            else None,
                            "design_quality": int(row["design_quality"])
                            if row["design_quality"]
                            else None,
                        }
                        break

        # Find first unrated design
        CURRENT_INDEX = 0
        for i in range(len(DESIGNS)):
            rating = RATINGS.get(i, {})
            if not all(
                [
                    rating.get("assemblability"),
                    rating.get("prompt_satisfaction"),
                    rating.get("design_quality"),
                ]
            ):
                CURRENT_INDEX = i
                break
    else:
        RATINGS = {}
        CURRENT_INDEX = 0

    return redirect(url_for("review", index=CURRENT_INDEX))


@app.route("/review/<int:index>")
def review(index: int):
    """Show review page for a specific design."""
    global CURRENT_INDEX

    if not REVIEWER_NAME:
        return redirect(url_for("index"))

    if index >= len(DESIGNS):
        index = len(DESIGNS) - 1

    if index < 0:
        index = 0

    if DESIGNS[index]["last_iteration"] is None:
        return redirect(url_for("review", index=index + 1))

    CURRENT_INDEX = index
    design = DESIGNS[index]
    ratings = RATINGS.get(index, {})

    def _fully_scored(i):
        if DESIGNS[i]["last_iteration"] is None:
            return True
        r = RATINGS.get(i, {})
        return all([r.get("assemblability"), r.get("prompt_satisfaction"), r.get("design_quality")])

    scored_count = sum(1 for i in range(len(DESIGNS)) if _fully_scored(i))

    if scored_count == len(DESIGNS):
        save_ratings_to_csv()
        csv_filename = f"{REVIEWER_NAME}_ratings.csv"
        return render_template_string(
            HTML_TEMPLATE, page="complete", total=len(DESIGNS), csv_file=csv_filename
        )

    next_unscored = None
    for i in list(range(index + 1, len(DESIGNS))) + list(range(0, index)):
        if not _fully_scored(i):
            next_unscored = i
            break

    prev_unscored = None
    for i in list(range(index - 1, -1, -1)) + list(range(len(DESIGNS) - 1, index, -1)):
        if not _fully_scored(i):
            prev_unscored = i
            break

    test_results = None
    test_results_path = (
        Path(EXPERIMENT_PATH)
        / design["model_type"]
        / design["exp_id"]
        / design["last_iteration"]
        / "test_results.json"
    )
    if test_results_path.exists():
        try:
            with open(test_results_path, "r") as f:
                test_results = json.load(f)
        except Exception:
            pass

    return render_template_string(
        HTML_TEMPLATE,
        page="review",
        design=design,
        current=index,
        total=len(DESIGNS),
        reviewer=REVIEWER_NAME,
        ratings=ratings,
        test_results=test_results,
        scored_count=scored_count,
        next_unscored=next_unscored,
        prev_unscored=prev_unscored,
    )


@app.route("/rate", methods=["POST"])
def rate():
    """Save a rating."""
    data = request.json
    index = data["index"]
    category = data["category"]
    value = data["value"]

    if index not in RATINGS:
        RATINGS[index] = {}

    RATINGS[index][category] = value

    # Auto-save to CSV
    save_ratings_to_csv()

    return jsonify({"status": "ok"})


@app.route("/media/<path:filepath>")
def serve_media(filepath):
    """Serve media files from the experiment directory."""
    return send_from_directory(EXPERIMENT_PATH, filepath)


# =============================================================================
# ANALYTICS FUNCTIONS
# =============================================================================


def load_all_ratings(experiment_path: str) -> pd.DataFrame:
    """Load all rating CSV files from the experiment directory."""
    experiment_path = Path(experiment_path)
    all_ratings = []

    # Find all *_ratings.csv files
    for csv_file in experiment_path.glob("*_ratings.csv"):
        reviewer_name = csv_file.stem.replace("_ratings", "")

        try:
            df = pd.read_csv(csv_file)
            df["reviewer"] = reviewer_name
            all_ratings.append(df)
            print(f"  Loaded {len(df)} ratings from {reviewer_name}")
        except Exception as e:
            print(f"  Warning: Could not load {csv_file}: {e}")

    if not all_ratings:
        return pd.DataFrame()

    return pd.concat(all_ratings, ignore_index=True)


def load_generation_times(experiment_path: str) -> pd.DataFrame:
    """Load generation times from info.json files."""
    experiment_path = Path(experiment_path)
    times = []

    for model_dir in experiment_path.iterdir():
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue

        model_type = model_dir.name

        for exp_dir in model_dir.iterdir():
            if not exp_dir.is_dir() or exp_dir.name.startswith("."):
                continue

            metrics_file = exp_dir / "run_metrics.json"
            if metrics_file.exists():
                try:
                    with open(metrics_file, "r") as f:
                        metrics = json.load(f)
                    generation_time = metrics.get("elapsed_wall_time_s")
                    if generation_time is not None:
                        times.append(
                            {
                                "model_type": model_type,
                                "experiment_name": exp_dir.name,
                                "generation_time": generation_time,
                            }
                        )
                except Exception:
                    pass

    return pd.DataFrame(times)


def run_analytics(experiment_path: str):
    """Run analytics on the collected ratings."""
    if not ANALYTICS_AVAILABLE:
        print("Error: pandas and matplotlib are required for analytics.")
        print("Install with: pip install pandas matplotlib numpy")
        sys.exit(1)

    experiment_path = Path(experiment_path)
    output_dir = experiment_path / "analytics"
    output_dir.mkdir(exist_ok=True)

    print("Loading ratings...")
    df = load_all_ratings(str(experiment_path))

    if df.empty:
        print(
            "Error: No ratings found. Make sure there are *_ratings.csv files in the directory."
        )
        sys.exit(1)

    # Filter out rows with missing ratings
    metrics = ["prompt_satisfaction", "assemblability", "design_quality"]
    df_valid = df.dropna(subset=metrics)
    df_valid = df_valid[df_valid[metrics].apply(lambda x: x != "").all(axis=1)]

    # Convert to numeric
    for m in metrics:
        df_valid[m] = pd.to_numeric(df_valid[m], errors="coerce")

    df_valid = df_valid.dropna(subset=metrics)

    print(
        f"\nAnalyzing {len(df_valid)} valid ratings from {df_valid['reviewer'].nunique()} reviewers"
    )
    print(f"Models: {', '.join(df_valid['model_type'].unique())}")
    print(f"Reviewers: {', '.join(df_valid['reviewer'].unique())}")

    # Model display names and ordering
    MODEL_DISPLAY_NAMES = {
        "sft": "SFT",
        "grpo": "GRPO",
        "web-auto": "Designer-QA",
        "web-single": "Designer",
    }
    MODEL_ORDER = ["sft", "grpo", "web-auto", "web-single"]

    def get_model_display_name(model):
        return MODEL_DISPLAY_NAMES.get(model, model)

    def get_ordered_models(models_list):
        """Return models in the correct display order, filtered to only those present."""
        return [m for m in MODEL_ORDER if m in models_list]

    def get_display_labels(models_list):
        """Return display names for models in order."""
        ordered = get_ordered_models(models_list)
        return [get_model_display_name(m) for m in ordered]

    # ==========================================================================
    # 1. Average score per metric per model per reviewer
    # ==========================================================================
    print("\n" + "=" * 60)
    print("AVERAGE SCORES PER METRIC PER MODEL PER REVIEWER")
    print("=" * 60)

    reviewer_model_stats = df_valid.groupby(["reviewer", "model_type"])[metrics].mean()
    print(reviewer_model_stats.round(2).to_string())

    # Save to CSV
    reviewer_model_stats.round(3).to_csv(
        output_dir / "scores_per_reviewer_per_model.csv"
    )

    # ==========================================================================
    # 2. Average score per metric per model (all reviewers)
    # ==========================================================================
    print("\n" + "=" * 60)
    print("AVERAGE SCORES PER METRIC PER MODEL (ALL REVIEWERS)")
    print("=" * 60)

    model_stats = df_valid.groupby("model_type")[metrics].agg(["mean", "std", "count"])
    print(model_stats.round(2).to_string())

    # Simplified view
    model_means = df_valid.groupby("model_type")[metrics].mean()
    print("\nSimplified (means only):")
    print(model_means.round(2).to_string())

    # Save to CSV
    model_stats.round(3).to_csv(output_dir / "scores_per_model_detailed.csv")
    model_means.round(3).to_csv(output_dir / "scores_per_model.csv")

    # ==========================================================================
    # 3. Average generation time per model
    # ==========================================================================
    print("\n" + "=" * 60)
    print("AVERAGE GENERATION TIME PER MODEL")
    print("=" * 60)

    times_df = load_generation_times(str(experiment_path))
    if not times_df.empty:
        time_stats = times_df.groupby("model_type")["generation_time"].agg(
            ["mean", "std", "min", "max", "count"]
        )
        print(time_stats.round(2).to_string())
        time_stats.round(3).to_csv(output_dir / "generation_times.csv")
    else:
        print("No generation time data found.")

    # ==========================================================================
    # 4. Generate Graphs
    # ==========================================================================
    print("\n" + "=" * 60)
    print("GENERATING GRAPHS")
    print("=" * 60)

    # Set style
    plt.style.use("seaborn-v0_8-darkgrid")
    colors = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"]

    # Increase font sizes for presentations
    plt.rcParams.update(
        {
            "font.size": 14,
            "axes.titlesize": 16,
            "axes.labelsize": 14,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "legend.fontsize": 12,
            "figure.titlesize": 18,
        }
    )

    # Graph 1: Bar chart of average scores per model
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.suptitle("Average Scores by Model", fontsize=14, fontweight="bold")

    ordered_models = get_ordered_models(model_means.index.tolist())
    display_labels = get_display_labels(model_means.index.tolist())

    for idx, metric in enumerate(metrics):
        ax = axes[idx]
        data = model_means[metric].reindex(ordered_models)
        bars = ax.bar(display_labels, data.values, color=colors[: len(data)])
        ax.set_title(metric.replace("_", " ").title())
        ax.set_ylabel("Average Score")
        ax.set_ylim(1, 5)
        ax.axhline(y=3, color="gray", linestyle="--", alpha=0.5)

        # Add value labels on bars
        for bar, val in zip(bars, data.values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.05,
                f"{val:.2f}",
                ha="center",
                va="bottom",
                fontsize=10,
            )

        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

    plt.tight_layout()
    plt.savefig(output_dir / "scores_by_model.png", dpi=150, bbox_inches="tight")
    print("  Saved: scores_by_model.png")
    plt.close()

    # Graph 2: Grouped bar chart comparing all metrics
    fig, ax = plt.subplots(figsize=(10, 6))
    model_means_ordered = model_means.reindex(ordered_models)
    x = np.arange(len(model_means_ordered.index))
    width = 0.25

    for i, metric in enumerate(metrics):
        offset = (i - 1) * width
        bars = ax.bar(
            x + offset,
            model_means_ordered[metric],
            width,
            label=metric.replace("_", " ").title(),
            color=colors[i],
        )

    ax.set_ylabel("Average Score")
    ax.set_title("All Metrics by Model")
    ax.set_xticks(x)
    ax.set_xticklabels(display_labels, rotation=45, ha="right")
    ax.legend()
    ax.set_ylim(1, 5.5)

    plt.tight_layout()
    plt.savefig(output_dir / "metrics_comparison.png", dpi=150, bbox_inches="tight")
    print("  Saved: metrics_comparison.png")
    plt.close()

    # Graph 3: Box plots showing score distributions
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.suptitle("Score Distributions by Model", fontsize=14, fontweight="bold")

    all_models = df_valid["model_type"].unique().tolist()
    box_ordered_models = get_ordered_models(all_models)
    box_display_labels = get_display_labels(all_models)

    for idx, metric in enumerate(metrics):
        ax = axes[idx]
        data_to_plot = [
            df_valid[df_valid["model_type"] == m][metric].values
            for m in box_ordered_models
        ]

        bp = ax.boxplot(data_to_plot, labels=box_display_labels, patch_artist=True)
        for patch, color in zip(bp["boxes"], colors[: len(box_ordered_models)]):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)

        ax.set_title(metric.replace("_", " ").title())
        ax.set_ylabel("Score")
        ax.set_ylim(0.5, 5.5)
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

    plt.tight_layout()
    plt.savefig(output_dir / "score_distributions.png", dpi=150, bbox_inches="tight")
    print("  Saved: score_distributions.png")
    plt.close()

    # Graph 4: Heatmap of reviewer vs model scores (if multiple reviewers)
    if df_valid["reviewer"].nunique() > 1:
        for metric in metrics:
            pivot = df_valid.pivot_table(
                index="reviewer", columns="model_type", values=metric, aggfunc="mean"
            )
            # Reorder columns by MODEL_ORDER
            heatmap_ordered_models = get_ordered_models(list(pivot.columns))
            pivot = pivot.reindex(columns=heatmap_ordered_models)
            heatmap_display_labels = get_display_labels(heatmap_ordered_models)

            fig, ax = plt.subplots(figsize=(8, 6))
            im = ax.imshow(pivot.values, cmap="RdYlGn", aspect="auto", vmin=1, vmax=5)

            ax.set_xticks(np.arange(len(pivot.columns)))
            ax.set_yticks(np.arange(len(pivot.index)))
            ax.set_xticklabels(heatmap_display_labels, rotation=45, ha="right")
            ax.set_yticklabels(pivot.index)

            # Add value annotations
            for i in range(len(pivot.index)):
                for j in range(len(pivot.columns)):
                    val = pivot.values[i, j]
                    if not np.isnan(val):
                        ax.text(
                            j,
                            i,
                            f"{val:.2f}",
                            ha="center",
                            va="center",
                            color="black",
                            fontsize=10,
                        )

            ax.set_title(f"{metric.replace('_', ' ').title()} by Reviewer and Model")
            plt.colorbar(im, ax=ax, label="Score")

            plt.tight_layout()
            plt.savefig(
                output_dir / f"heatmap_{metric}.png", dpi=150, bbox_inches="tight"
            )
            print(f"  Saved: heatmap_{metric}.png")
            plt.close()

    # Graph 5: Generation time comparison (if data available)
    if not times_df.empty:
        fig, ax = plt.subplots(figsize=(10, 6))

        time_means = times_df.groupby("model_type")["generation_time"].mean()
        time_stds = times_df.groupby("model_type")["generation_time"].std()
        # Reorder by MODEL_ORDER
        time_ordered_models = get_ordered_models(list(time_means.index))
        time_means = time_means.reindex(time_ordered_models)
        time_stds = time_stds.reindex(time_ordered_models)
        time_display_labels = get_display_labels(time_ordered_models)

        bars = ax.bar(
            time_display_labels,
            time_means.values,
            yerr=time_stds.values,
            capsize=5,
            color=colors[: len(time_means)],
        )

        ax.set_ylabel("Generation Time (seconds)")
        ax.set_title("Average Generation Time by Model")
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

        # Add value labels
        for bar, val in zip(bars, time_means.values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.5,
                f"{val:.1f}s",
                ha="center",
                va="bottom",
                fontsize=10,
            )

        plt.tight_layout()
        plt.savefig(output_dir / "generation_times.png", dpi=150, bbox_inches="tight")
        print("  Saved: generation_times.png")
        plt.close()

    # Graph 6: Overall score (average of all metrics) per model
    df_valid["overall"] = df_valid[metrics].mean(axis=1)
    overall_by_model = df_valid.groupby("model_type")["overall"].agg(["mean", "std"])
    # Reorder by MODEL_ORDER
    overall_ordered_models = get_ordered_models(list(overall_by_model.index))
    overall_by_model = overall_by_model.reindex(overall_ordered_models)
    overall_display_labels = get_display_labels(overall_ordered_models)

    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.bar(
        overall_display_labels,
        overall_by_model["mean"],
        yerr=overall_by_model["std"],
        capsize=5,
        color=colors[: len(overall_by_model)],
    )

    ax.set_ylabel("Overall Score")
    ax.set_title("Overall Average Score by Model\n(Average of All Metrics)")
    ax.set_ylim(1, 5.5)
    ax.axhline(y=3, color="gray", linestyle="--", alpha=0.5)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

    for bar, val in zip(bars, overall_by_model["mean"].values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.1,
            f"{val:.2f}",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )

    plt.tight_layout()
    plt.savefig(output_dir / "overall_scores.png", dpi=150, bbox_inches="tight")
    print("  Saved: overall_scores.png")
    plt.close()

    # ==========================================================================
    # 5. Analytics by Distribution and Difficulty Level
    # ==========================================================================
    print("\n" + "=" * 60)
    print("ANALYTICS BY DISTRIBUTION AND DIFFICULTY LEVEL")
    print("=" * 60)

    # Load experiments.csv
    experiments_csv = Path(__file__).parent / "experiments.csv"
    if not experiments_csv.exists():
        experiments_csv = experiment_path / "experiments.csv"

    if experiments_csv.exists():
        experiments_df = pd.read_csv(experiments_csv)
        print(f"Loaded experiments.csv with {len(experiments_df)} prompts")

        # Convert experiment_id to int for joining (handle both str and int types)
        def to_prompt_id(x):
            try:
                return int(x)
            except (ValueError, TypeError):
                return None

        df_valid["prompt_id"] = df_valid["experiment_name"].apply(to_prompt_id)

        # Join on prompt_id
        df_with_meta = df_valid.merge(
            experiments_df[["prompt_id", "distribution", "difficulty_level"]],
            on="prompt_id",
            how="left",
        )

        # Check for successful joins
        matched = df_with_meta["distribution"].notna().sum()
        print(f"Matched {matched}/{len(df_with_meta)} ratings with experiment metadata")

        if matched > 0:
            df_meta = df_with_meta.dropna(subset=["distribution", "difficulty_level"])

            # --- By Distribution ---
            print("\n" + "-" * 40)
            print("SCORES BY DISTRIBUTION")
            print("-" * 40)

            dist_stats = df_meta.groupby(["model_type", "distribution"])[metrics].mean()
            print(dist_stats.round(2).to_string())
            dist_stats.round(3).to_csv(output_dir / "scores_by_distribution.csv")

            # Overall by distribution
            print("\nOverall by Distribution (all models):")
            dist_overall = df_meta.groupby("distribution")[metrics].mean()
            print(dist_overall.round(2).to_string())

            # --- By Difficulty Level ---
            print("\n" + "-" * 40)
            print("SCORES BY DIFFICULTY LEVEL")
            print("-" * 40)

            diff_stats = df_meta.groupby(["model_type", "difficulty_level"])[
                metrics
            ].mean()
            print(diff_stats.round(2).to_string())
            diff_stats.round(3).to_csv(output_dir / "scores_by_difficulty.csv")

            # Overall by difficulty
            print("\nOverall by Difficulty Level (all models):")
            diff_overall = df_meta.groupby("difficulty_level")[metrics].mean()
            print(diff_overall.round(2).to_string())

            # --- Combined: Distribution x Difficulty ---
            print("\n" + "-" * 40)
            print("SCORES BY DISTRIBUTION AND DIFFICULTY")
            print("-" * 40)

            combined_stats = df_meta.groupby(
                ["model_type", "distribution", "difficulty_level"]
            )[metrics].mean()
            print(combined_stats.round(2).to_string())
            combined_stats.round(3).to_csv(
                output_dir / "scores_by_distribution_difficulty.csv"
            )

            # ==========================================================================
            # Graphs for Distribution and Difficulty
            # ==========================================================================
            print("\n" + "-" * 40)
            print("GENERATING DISTRIBUTION/DIFFICULTY GRAPHS")
            print("-" * 40)

            # Graph: Scores by Distribution per Model
            fig, axes = plt.subplots(1, 3, figsize=(15, 5))
            fig.suptitle(
                "Scores by Distribution per Model", fontsize=14, fontweight="bold"
            )

            distributions = df_meta["distribution"].unique()
            models = get_ordered_models(list(df_meta["model_type"].unique()))
            models_display = get_display_labels(models)
            x = np.arange(len(models))
            width = 0.35

            for idx, metric in enumerate(metrics):
                ax = axes[idx]
                for i, dist in enumerate(sorted(distributions)):
                    data = (
                        df_meta[df_meta["distribution"] == dist]
                        .groupby("model_type")[metric]
                        .mean()
                    )
                    data = data.reindex(models, fill_value=0)
                    offset = (i - 0.5) * width
                    bars = ax.bar(
                        x + offset, data.values, width, label=dist, color=colors[i]
                    )

                ax.set_title(metric.replace("_", " ").title())
                ax.set_ylabel("Average Score")
                ax.set_xticks(x)
                ax.set_xticklabels(models_display, rotation=45, ha="right")
                ax.set_ylim(1, 5.5)
                ax.axhline(y=3, color="gray", linestyle="--", alpha=0.5)
                ax.legend()

            plt.tight_layout()
            plt.savefig(
                output_dir / "scores_by_distribution.png", dpi=150, bbox_inches="tight"
            )
            print("  Saved: scores_by_distribution.png")
            plt.close()

            # Graph: Overall Score by Distribution per Model (averaged across all metrics)
            fig, ax = plt.subplots(figsize=(10, 6))
            fig.suptitle(
                "Overall Score by Distribution per Model",
                fontsize=14,
                fontweight="bold",
            )

            # Calculate overall score (average of all metrics)
            df_meta["overall"] = df_meta[metrics].mean(axis=1)

            for i, dist in enumerate(sorted(distributions)):
                data = (
                    df_meta[df_meta["distribution"] == dist]
                    .groupby("model_type")["overall"]
                    .mean()
                )
                data = data.reindex(models, fill_value=0)
                offset = (i - 0.5) * width
                bars = ax.bar(
                    x + offset, data.values, width, label=dist, color=colors[i]
                )

            ax.set_ylabel("Overall Score")
            ax.set_xticks(x)
            ax.set_xticklabels(models_display, rotation=45, ha="right")
            ax.set_ylim(1, 5.5)
            ax.axhline(y=3, color="gray", linestyle="--", alpha=0.5)
            ax.legend()

            plt.tight_layout()
            plt.savefig(
                output_dir / "overall_by_distribution.png", dpi=150, bbox_inches="tight"
            )
            print("  Saved: overall_by_distribution.png")
            plt.close()

            # Graph: Scores by Difficulty Level per Model
            fig, axes = plt.subplots(1, 3, figsize=(15, 5))
            fig.suptitle(
                "Scores by Difficulty Level per Model", fontsize=14, fontweight="bold"
            )

            difficulty_levels = sorted(df_meta["difficulty_level"].unique())
            diff_colors = [
                "#22c55e",
                "#f59e0b",
                "#ef4444",
            ]  # Easy=green, Medium=yellow, Hard=red

            for idx, metric in enumerate(metrics):
                ax = axes[idx]
                n_levels = len(difficulty_levels)
                width = 0.8 / n_levels

                for i, level in enumerate(difficulty_levels):
                    data = (
                        df_meta[df_meta["difficulty_level"] == level]
                        .groupby("model_type")[metric]
                        .mean()
                    )
                    data = data.reindex(models, fill_value=0)
                    offset = (i - (n_levels - 1) / 2) * width
                    bars = ax.bar(
                        x + offset,
                        data.values,
                        width,
                        label=f"Level {level}",
                        color=diff_colors[i % len(diff_colors)],
                    )

                ax.set_title(metric.replace("_", " ").title())
                ax.set_ylabel("Average Score")
                ax.set_xticks(x)
                ax.set_xticklabels(models_display, rotation=45, ha="right")
                ax.set_ylim(1, 5.5)
                ax.axhline(y=3, color="gray", linestyle="--", alpha=0.5)
                ax.legend()

            plt.tight_layout()
            plt.savefig(
                output_dir / "scores_by_difficulty.png", dpi=150, bbox_inches="tight"
            )
            print("  Saved: scores_by_difficulty.png")
            plt.close()

            # Graph: Heatmap of Model x Distribution (overall score)
            df_meta["overall"] = df_meta[metrics].mean(axis=1)

            pivot_dist = df_meta.pivot_table(
                index="model_type",
                columns="distribution",
                values="overall",
                aggfunc="mean",
            )
            # Reorder rows by MODEL_ORDER
            pivot_dist_ordered = get_ordered_models(list(pivot_dist.index))
            pivot_dist = pivot_dist.reindex(pivot_dist_ordered)
            pivot_dist_display = get_display_labels(pivot_dist_ordered)

            fig, ax = plt.subplots(figsize=(8, 6))
            im = ax.imshow(
                pivot_dist.values, cmap="RdYlGn", aspect="auto", vmin=1, vmax=3
            )

            ax.set_xticks(np.arange(len(pivot_dist.columns)))
            ax.set_yticks(np.arange(len(pivot_dist.index)))
            ax.set_xticklabels(pivot_dist.columns)
            ax.set_yticklabels(pivot_dist_display)

            for i in range(len(pivot_dist.index)):
                for j in range(len(pivot_dist.columns)):
                    val = pivot_dist.values[i, j]
                    if not np.isnan(val):
                        ax.text(
                            j,
                            i,
                            f"{val:.2f}",
                            ha="center",
                            va="center",
                            color="black",
                            fontsize=12,
                            fontweight="bold",
                        )

            ax.set_title("Overall Score: Model × Distribution")
            plt.colorbar(im, ax=ax, label="Score")

            plt.tight_layout()
            plt.savefig(
                output_dir / "heatmap_model_distribution.png",
                dpi=150,
                bbox_inches="tight",
            )
            print("  Saved: heatmap_model_distribution.png")
            plt.close()

            # Graph: Heatmap of Model x Difficulty
            pivot_diff = df_meta.pivot_table(
                index="model_type",
                columns="difficulty_level",
                values="overall",
                aggfunc="mean",
            )
            # Reorder rows by MODEL_ORDER
            pivot_diff_ordered = get_ordered_models(list(pivot_diff.index))
            pivot_diff = pivot_diff.reindex(pivot_diff_ordered)
            pivot_diff_display = get_display_labels(pivot_diff_ordered)

            fig, ax = plt.subplots(figsize=(8, 6))
            im = ax.imshow(
                pivot_diff.values, cmap="RdYlGn", aspect="auto", vmin=1, vmax=3
            )

            ax.set_xticks(np.arange(len(pivot_diff.columns)))
            ax.set_yticks(np.arange(len(pivot_diff.index)))
            ax.set_xticklabels([f"Level {c}" for c in pivot_diff.columns])
            ax.set_yticklabels(pivot_diff_display)

            for i in range(len(pivot_diff.index)):
                for j in range(len(pivot_diff.columns)):
                    val = pivot_diff.values[i, j]
                    if not np.isnan(val):
                        ax.text(
                            j,
                            i,
                            f"{val:.2f}",
                            ha="center",
                            va="center",
                            color="black",
                            fontsize=12,
                            fontweight="bold",
                        )

            ax.set_title("Overall Score: Model × Difficulty Level")
            plt.colorbar(im, ax=ax, label="Score")

            plt.tight_layout()
            plt.savefig(
                output_dir / "heatmap_model_difficulty.png",
                dpi=150,
                bbox_inches="tight",
            )
            print("  Saved: heatmap_model_difficulty.png")
            plt.close()

            # Graph: Line plot showing performance across difficulty levels
            fig, ax = plt.subplots(figsize=(10, 6))

            for i, model in enumerate(models):
                model_data = (
                    df_meta[df_meta["model_type"] == model]
                    .groupby("difficulty_level")["overall"]
                    .mean()
                )
                ax.plot(
                    model_data.index,
                    model_data.values,
                    marker="o",
                    linewidth=2,
                    markersize=8,
                    label=get_model_display_name(model),
                    color=colors[i % len(colors)],
                )

            ax.set_xlabel("Difficulty Level")
            ax.set_ylabel("Overall Score")
            ax.set_title("Performance Across Difficulty Levels by Model")
            ax.set_ylim(1, 5.5)
            ax.axhline(y=3, color="gray", linestyle="--", alpha=0.5)
            ax.legend()
            ax.set_xticks(difficulty_levels)

            plt.tight_layout()
            plt.savefig(
                output_dir / "difficulty_trend.png", dpi=150, bbox_inches="tight"
            )
            print("  Saved: difficulty_trend.png")
            plt.close()

    else:
        print(
            "Warning: experiments.csv not found. Skipping distribution/difficulty analytics."
        )
        print(f"  Looked in: {experiments_csv}")

    # ==========================================================================
    # Summary
    # ==========================================================================
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total ratings analyzed: {len(df_valid)}")
    print(f"Number of reviewers: {df_valid['reviewer'].nunique()}")
    print(f"Number of models: {df_valid['model_type'].nunique()}")
    print(f"\nOutput saved to: {output_dir}")
    print("\nFiles generated:")
    for f in sorted(output_dir.iterdir()):
        print(f"  - {f.name}")


def main():
    global EXPERIMENT_PATH, DESIGNS

    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Design Review Tool")
        print("=" * 50)
        print("\\nUsage:")
        print("  Human review (web interface):")
        print("    python collect_results.py <experiment_outputs_path>")
        print("\\n  Gemini LLM review:")
        print(
            "    python collect_results.py <experiment_outputs_path> --gemini <api_key>"
        )
        print("\\n  Analytics:")
        print("    python collect_results.py <experiment_outputs_path> --analyze")
        print("\\nExamples:")
        print("  python collect_results.py ./experiment_outputs")
        print("  python collect_results.py ./experiment_outputs --gemini AIza...")
        print("  python collect_results.py ./experiment_outputs --analyze")
        sys.exit(1)

    experiment_path = os.path.abspath(sys.argv[1])

    if not os.path.isdir(experiment_path):
        print(f"Error: Directory not found: {experiment_path}")
        sys.exit(1)

    # Check for mode
    if "--analyze" in sys.argv:
        run_analytics(experiment_path)
    elif "--gemini" in sys.argv:
        gemini_idx = sys.argv.index("--gemini")
        if gemini_idx + 1 >= len(sys.argv):
            print("Error: --gemini flag requires an API key")
            sys.exit(1)
        api_key = sys.argv[gemini_idx + 1]
        run_gemini_review(experiment_path, api_key)
    else:
        # Human review mode
        EXPERIMENT_PATH = experiment_path

        print(f"Loading designs from: {EXPERIMENT_PATH}")
        DESIGNS = load_designs(EXPERIMENT_PATH)

        # Randomize order of designs
        random.shuffle(DESIGNS)

        if not DESIGNS:
            print("Error: No designs found in the specified directory.")
            print("Expected structure:")
            print("  experiment_outputs/")
            print("    model_type/")
            print("      experiment_id/")
            print("        design.gif, design.png, design.stl, info.json")
            sys.exit(1)

        print(f"Found {len(DESIGNS)} designs to review")
        print("\\n" + "=" * 50)
        print("Starting Design Review Tool")
        print("Open your browser to: http://127.0.0.1:5000")
        print("=" * 50 + "\\n")

        app.run(debug=False, port=5000)


if __name__ == "__main__":
    main()