import { ChevronRight, Database, Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { ConfigActions } from "../SyncSetupUi.jsx";

export default function ConnectionEditor({
  configData,
  validation,
  isDirty,
  isLoading,
  isSaving,
  testingDbId,
  testingWriteId,
  onReload,
  onSave,
  onAddConnection,
  onPatchConnection,
  onRemoveConnection,
  onTestDatabase,
  onTestWrite,
  connectionUsageCount,
  toNumber,
}) {
  const [expandedIds, setExpandedIds] = useState(new Set(["default"]));

  function toggleExpanded(connectionId) {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(connectionId)) {
        next.delete(connectionId);
      } else {
        next.add(connectionId);
      }
      return next;
    });
  }

  return (
    <section className="setupSection">
      <div className="sectionTitle withAction">
        <div>
          <Database size={18} aria-hidden="true" />
          <h3>SQL servers</h3>
        </div>
        <ConfigActions
          isDirty={isDirty}
          isLoading={isLoading}
          isSaving={isSaving}
          canSave={Boolean(configData) && !validation.hasErrors}
          onReload={onReload}
          onSave={onSave}
          leading={(
            <>
              <button type="button" className="secondaryButton" onClick={() => onAddConnection("postgresql")}>
                <Plus size={16} aria-hidden="true" />
                PostgreSQL
              </button>
              <button type="button" className="secondaryButton" onClick={() => onAddConnection("sqlserver")}>
                <Plus size={16} aria-hidden="true" />
                SQL Server
              </button>
            </>
          )}
        />
      </div>
      <div className="connectionList">
        {(configData.database_connections || []).map((connection, index) => {
          const usage = connectionUsageCount(connection.id);
          const isSqlServer = connection.engine === "sqlserver";
          const isExpanded = expandedIds.has(connection.id);
          return (
            <article className={`connectionCard ${isExpanded ? "expanded" : "collapsed"}`} key={`${connection.id}-${index}`}>
              <div className="jobCardHeader">
                <button
                  type="button"
                  className="connectionSummaryButton"
                  onClick={() => toggleExpanded(connection.id)}
                  aria-expanded={isExpanded}
                >
                  <ChevronRight size={16} aria-hidden="true" />
                  <span>
                    <strong>{connection.name || connection.id}</strong>
                    <small>{connection.engine} · {connection.host || "localhost"}:{connection.port || (isSqlServer ? 1433 : 5432)} · {usage} job</small>
                  </span>
                </button>
                <div className="rowActions">
                  <button type="button" className="secondaryButton" onClick={() => onTestDatabase(connection.id)} disabled={Boolean(testingDbId)}>
                    <Play size={15} aria-hidden="true" />
                    {testingDbId === connection.id ? "Đang test" : "Test"}
                  </button>
                  <button type="button" className="secondaryButton" onClick={() => onTestWrite(connection.id, connection.schema)} disabled={Boolean(testingWriteId)}>
                    <Play size={15} aria-hidden="true" />
                    {testingWriteId === connection.id ? "Đang test ghi" : "Test ghi"}
                  </button>
                  <button type="button" className="iconButton danger" title="Xóa server" onClick={() => onRemoveConnection(index)} disabled={usage > 0 || (configData.database_connections || []).length <= 1}>
                    <Trash2 size={15} aria-hidden="true" />
                  </button>
                </div>
              </div>
              {isExpanded && (
                <div className="setupGrid">
                  <label>
                    ID
                    <input value={connection.id || ""} onChange={(event) => onPatchConnection(index, { id: event.target.value })} />
                  </label>
                  <label>
                    Tên hiển thị
                    <input value={connection.name || ""} onChange={(event) => onPatchConnection(index, { name: event.target.value })} />
                  </label>
                  <label>
                    Engine
                    <select value={connection.engine || "postgresql"} onChange={(event) => onPatchConnection(index, { engine: event.target.value })}>
                      <option value="postgresql">PostgreSQL</option>
                      <option value="sqlserver">Microsoft SQL Server</option>
                    </select>
                  </label>
                  <label>
                    Host
                    <input value={connection.host || ""} onChange={(event) => onPatchConnection(index, { host: event.target.value })} />
                  </label>
                  <label>
                    Port
                    <input type="number" min="1" value={connection.port ?? ""} onChange={(event) => onPatchConnection(index, { port: toNumber(event.target.value, isSqlServer ? 1433 : 5432) })} />
                  </label>
                  <label>
                    Database
                    <input value={connection.database || ""} onChange={(event) => onPatchConnection(index, { database: event.target.value })} />
                  </label>
                  <label>
                    User
                    <input value={connection.user || ""} onChange={(event) => onPatchConnection(index, { user: event.target.value })} />
                  </label>
                  <label>
                    Password / biến môi trường
                    <input type="password" autoComplete="off" value={connection.password || ""} onChange={(event) => onPatchConnection(index, { password: event.target.value })} />
                  </label>
                  <label>
                    Schema mặc định
                    <input value={connection.schema || ""} onChange={(event) => onPatchConnection(index, { schema: event.target.value })} />
                  </label>
                  {isSqlServer && (
                    <>
                      <label className="wideField">
                        ODBC driver
                        <input value={connection.driver || ""} onChange={(event) => onPatchConnection(index, { driver: event.target.value })} />
                      </label>
                      <label className="checkField">
                        <input type="checkbox" checked={Boolean(connection.trusted_connection)} onChange={(event) => onPatchConnection(index, { trusted_connection: event.target.checked })} />
                        Windows trusted connection
                      </label>
                      <label className="checkField">
                        <input type="checkbox" checked={Boolean(connection.encrypt)} onChange={(event) => onPatchConnection(index, { encrypt: event.target.checked })} />
                        Encrypt
                      </label>
                      <label className="checkField">
                        <input type="checkbox" checked={Boolean(connection.trust_server_certificate)} onChange={(event) => onPatchConnection(index, { trust_server_certificate: event.target.checked })} />
                        Trust server certificate
                      </label>
                    </>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
