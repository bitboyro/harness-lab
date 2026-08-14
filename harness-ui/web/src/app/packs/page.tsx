import { PacksListClient } from "./PacksListClient";

export default function PacksIndexPage() {
  return (
    <div>
      <p className="section-label">Task packs</p>
      <h1 className="page-title">Packs</h1>
      <p className="page-lede">
        YAML task packs on disk — draft from a target or edit directly.
      </p>
      <PacksListClient />
    </div>
  );
}
