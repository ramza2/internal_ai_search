import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="card" style={{ margin: "2rem auto", maxWidth: 480, textAlign: "center" }}>
      <h1 className="pageTitle">404</h1>
      <p>페이지를 찾을 수 없습니다.</p>
      <Link to="/search">검색으로 돌아가기</Link>
    </div>
  );
}
