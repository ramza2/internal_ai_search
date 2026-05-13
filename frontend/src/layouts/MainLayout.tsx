import { Outlet } from "react-router-dom";
import { Header } from "@/components/Header";
import { Sidebar } from "@/components/Sidebar";
import styles from "./MainLayout.module.css";

export function MainLayout() {
  return (
    <div className={styles.shell}>
      <Sidebar />
      <div className={styles.main}>
        <Header />
        <main className={styles.content}>
          <div className="pageShell">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
