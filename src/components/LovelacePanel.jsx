const HA_DASHBOARD = "http://ha.chaos.home/lovelace/0?kiosk";

export default function LovelacePanel() {
  return (
    <iframe
      className="lovelace-frame"
      src={HA_DASHBOARD}
      title="Home Assistant"
    />
  );
}
