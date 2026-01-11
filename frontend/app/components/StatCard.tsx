type StatCardProps = {
  label: string;
  value: string | number;
  accent?: 'primary' | 'danger';
  helper?: string;
};

export function StatCard({ label, value, accent = 'primary', helper }: StatCardProps) {
  const pillClass = accent === 'danger' ? 'pill danger' : 'pill';
  return (
    <div className="card">
      <div className={pillClass}>{label}</div>
      <div style={{ fontSize: 32, fontWeight: 700, marginTop: 12 }}>{value}</div>
      {helper ? <div className="muted" style={{ marginTop: 4 }}>{helper}</div> : null}
    </div>
  );
}
