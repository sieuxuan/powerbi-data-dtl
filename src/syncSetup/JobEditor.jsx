export default function JobEditor({ children, isEditing }) {
  return (
    <article className={`jobEditor ${isEditing ? "editing" : "compact"}`}>
      {children}
    </article>
  );
}
