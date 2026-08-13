export default function SettingsPage() {
  return (
    <div className="p-6 flex flex-col gap-4" style={{ background: "var(--background)", minHeight: "calc(100vh - 96px)" }}>
      <div>
        <h1 className="text-xl font-bold" style={{ color: "var(--text)" }}>Settings</h1>
        <p className="text-sm mt-1" style={{ color: "var(--muted2)" }}>More settings coming soon.</p>
      </div>
    </div>
  );
}
