// A gridded xenon ion thruster between the lowest and highest throttle points of NASA's NSTAR engine.
// Thrust is the momentum of the beam: T = gamma * I * sqrt(2 * M * V / e).
export const MODEL = (() => {
  const E = 1.602176634e-19; // C
  const XENON = 131.293 * 1.66053907e-27; // kg per ion
  const GAMMA = 0.958; // beam divergence and doubly charged ions
  const LOW = { volts: 650, amps: 0.51 };
  const HIGH = { volts: 1100, amps: 1.76 };
  const at = (level) => {
    const u = Math.min(1, Math.max(0, level));
    const volts = Math.round(LOW.volts + (HIGH.volts - LOW.volts) * u);
    const amps = LOW.amps + (HIGH.amps - LOW.amps) * u;
    const speed = Math.sqrt((2 * E * volts) / XENON); // m/s
    const thrust = GAMMA * amps * Math.sqrt((2 * XENON * volts) / E) * 1000; // mN
    return { volts, amps, speed: speed / 1000, thrust, share: amps / HIGH.amps, hot: (volts - LOW.volts) / (HIGH.volts - LOW.volts) };
  };
  return { LOW, HIGH, at };
})();
