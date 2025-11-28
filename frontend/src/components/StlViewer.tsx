import { useState, useEffect, useRef } from 'react';
import { Canvas, useThree } from '@react-three/fiber';
import { TrackballControls } from '@react-three/drei';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import * as THREE from 'three';

// STL Model component that loads and displays the model
function StlModel({ url }: { url: string }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [geometry, setGeometry] = useState<THREE.BufferGeometry | null>(null);
  const { camera } = useThree();

  useEffect(() => {
    const loader = new STLLoader();
    loader.load(url, (geo) => {
      geo.computeVertexNormals();
      geo.center();
      setGeometry(geo);

      // Auto-fit camera to model
      geo.computeBoundingBox();
      if (geo.boundingBox) {
        const box = geo.boundingBox;
        const size = new THREE.Vector3();
        box.getSize(size);
        const maxDim = Math.max(size.x, size.y, size.z);
        const distance = maxDim * 2.5;
        
        camera.position.set(distance, distance, distance);
        camera.lookAt(0, 0, 0);
        
        // Adjust clipping planes based on model size
        if (camera instanceof THREE.PerspectiveCamera) {
          camera.near = maxDim * 0.01;
          camera.far = maxDim * 100;
          camera.updateProjectionMatrix();
        }
      }
    });
  }, [url, camera]);

  if (!geometry) {
    return null;
  }

  return (
    <mesh ref={meshRef} geometry={geometry}>
      <meshStandardMaterial 
        color="#D2B48C" 
        roughness={0.4} 
        metalness={0.3}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

// Axis helper component showing X (red), Y (green), Z (blue) arrows at origin
function AxisHelper({ size = 50 }: { size?: number }) {
  return (
    <group>
      {/* X axis - Red */}
      <arrowHelper args={[new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, 0), size, 0xff0000, size * 0.15, size * 0.08]} />
      {/* Y axis - Green */}
      <arrowHelper args={[new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 0), size, 0x00ff00, size * 0.15, size * 0.08]} />
      {/* Z axis - Blue */}
      <arrowHelper args={[new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 0, 0), size, 0x0000ff, size * 0.15, size * 0.08]} />
      {/* Origin sphere */}
      <mesh position={[0, 0, 0]}>
        <sphereGeometry args={[size * 0.03, 16, 16]} />
        <meshBasicMaterial color={0xffffff} />
      </mesh>
    </group>
  );
}

// Main STL Viewer component - this is the default export for lazy loading
export default function StlViewer({ url }: { url: string }) {
  const [error, setError] = useState<string | null>(null);

  if (error) {
    return (
      <div className="stl-error">
        <p>Failed to load 3D model</p>
        <p className="stl-error-detail">{error}</p>
      </div>
    );
  }

  return (
    <Canvas
      camera={{ position: [100, 100, 100], fov: 50, near: 0.1, far: 10000 }}
      style={{ height: '300px', background: '#1a1a2e' }}
      onError={() => setError('Failed to initialize 3D viewer')}
    >
      <ambientLight intensity={0.6} />
      <directionalLight position={[10, 10, 10]} intensity={1} />
      <directionalLight position={[-10, -10, -10]} intensity={0.5} />
      <directionalLight position={[0, 10, 0]} intensity={0.3} />
      <StlModel url={url} />
      {/* <AxisHelper /> */}
      <TrackballControls rotateSpeed={4.0} />
    </Canvas>
  );
}
