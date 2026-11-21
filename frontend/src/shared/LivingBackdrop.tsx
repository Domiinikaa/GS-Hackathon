// Fixed ambient layer behind every glass surface. Which glow is lit is decided in CSS
// from <html data-mood>, set by useSystemMood.
export default function LivingBackdrop() {
  return (
    <div className="backdrop" aria-hidden="true">
      <div className="backdrop__blob backdrop__blob--indigo" />
      <div className="backdrop__blob backdrop__blob--amber" />
      <div className="backdrop__glow backdrop__glow--clear" />
      <div className="backdrop__glow backdrop__glow--warning" />
      <div className="backdrop__glow backdrop__glow--critical" />
    </div>
  );
}
