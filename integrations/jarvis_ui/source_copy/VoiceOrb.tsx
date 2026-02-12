import type { MissionMode } from "../../shared/contracts";

interface VoiceOrbProps {
  level: number;
  mode: MissionMode;
}

export const VoiceOrb = ({ level, mode }: VoiceOrbProps): JSX.Element => {
  const scale = 1 + level * 0.28;
  const glow = 0.35 + level * 0.65;

  return (
    <div className={`voice-orb mode-${mode}`} style={{ ["--orb-scale" as string]: scale }}>
      <div className="orb-core" style={{ opacity: glow }} />
      <div className="orb-wave orb-wave-a" />
      <div className="orb-wave orb-wave-b" />
      <div className="orb-text">
        <span>JARVIS</span>
        <small>{Math.round(level * 100)}% input</small>
      </div>
    </div>
  );
};
