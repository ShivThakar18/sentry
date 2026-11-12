/**
 * <Placeholder>: a stand-in screen until the real one is built.
 * Shows the route's :id too, so you can check the detail routes work.
 */
import { useParams } from "react-router-dom";
import styles from "./Screen.module.css";

export function Placeholder({ title }: { title: string }) {
  // useParams() reads the :id part of routes like /fleet/:id.
  const { id } = useParams();
  return (
    <div className={styles.content}>
      <h1 className={styles.title}>{title}</h1>
      {id && <p className={styles.sub}>id: {id}</p>}
    </div>
  );
}
