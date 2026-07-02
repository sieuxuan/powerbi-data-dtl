export default function Wizard({ children, onClose }) {
  return (
    <section className="setupSection wizardPanel">
      <div className="wizardHeader">
        <div>
          <p className="eyebrow">Thêm tác vụ đồng bộ</p>
          <h3>Chọn nguồn → Xem trước → Ghép cột vào bảng</h3>
        </div>
        <button type="button" className="secondaryButton" onClick={onClose}>
          Đóng
        </button>
      </div>
      {children}
    </section>
  );
}
