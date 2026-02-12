import { useEffect, useRef, useState } from "react";

export const useMicLevel = (): number => {
  const [level, setLevel] = useState(0.12);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    let audioContext: AudioContext | null = null;
    let analyser: AnalyserNode | null = null;
    let dataArray: Uint8Array | null = null;
    let stream: MediaStream | null = null;
    let fallbackInterval: number | null = null;

    const fallback = () => {
      fallbackInterval = window.setInterval(() => {
        setLevel((current) => {
          const drift = (Math.random() - 0.5) * 0.08;
          return Math.max(0.08, Math.min(0.32, current + drift));
        });
      }, 220);
    };

    const loop = () => {
      if (!analyser || !dataArray) {
        return;
      }
      analyser.getByteFrequencyData(dataArray as unknown as Uint8Array<ArrayBuffer>);
      const total = dataArray.reduce((acc, value) => acc + value, 0);
      const avg = total / dataArray.length / 255;
      setLevel(Math.max(0.05, Math.min(1, avg * 1.8)));
      rafRef.current = requestAnimationFrame(loop);
    };

    const init = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioContext = new window.AudioContext();
        const source = audioContext.createMediaStreamSource(stream);
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 128;
        dataArray = new Uint8Array(analyser.frequencyBinCount);
        source.connect(analyser);
        loop();
      } catch {
        fallback();
      }
    };

    void init();

    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
      }
      if (fallbackInterval) {
        clearInterval(fallbackInterval);
      }
      stream?.getTracks().forEach((track) => track.stop());
      void audioContext?.close();
    };
  }, []);

  return level;
};
