import React, { useEffect, useRef } from 'react';

interface VoiceVisualizerProps {
  analyser: AnalyserNode | null;
  isPaused: boolean;
}

export const VoiceVisualizer: React.FC<VoiceVisualizerProps> = ({ analyser, isPaused }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const requestRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !analyser) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      // Loop the animation
      requestRef.current = requestAnimationFrame(draw);

      if (isPaused) {
        // Just draw a flat line if paused, don't update data
        dataArray.fill(128); // 128 is silence in byte representation
      } else {
        analyser.getByteTimeDomainData(dataArray);
      }

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      ctx.lineWidth = 2;
      ctx.strokeStyle = 'rgba(16, 185, 129, 0.8)'; // emerald-500
      ctx.beginPath();

      const sliceWidth = canvas.width * 1.0 / bufferLength;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        // v goes from 0.0 to 2.0 (1.0 is middle/silence)
        const v = dataArray[i] / 128.0;
        // Map 1.0 to center of canvas
        const y = v * (canvas.height / 2);

        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }

        x += sliceWidth;
      }

      ctx.lineTo(canvas.width, canvas.height / 2);
      ctx.stroke();
    };

    requestRef.current = requestAnimationFrame(draw);

    return () => {
      if (requestRef.current) {
        cancelAnimationFrame(requestRef.current);
      }
    };
  }, [analyser, isPaused]);

  return (
    <canvas 
      ref={canvasRef} 
      width={100} 
      height={24} 
      style={{ 
        width: '100px', 
        height: '24px', 
        borderRadius: '4px',
        backgroundColor: 'rgba(0, 0, 0, 0.1)',
        border: '1px solid var(--glass-border)'
      }} 
    />
  );
};
