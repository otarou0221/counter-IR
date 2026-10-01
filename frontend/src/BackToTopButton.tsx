import { useEffect, useState } from "react";

type Props = {
  targetId: string;
  label?: string;
};

export default function BackToTopButton({ targetId, label = "ページ上部へ戻る" }: Props) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const target = document.getElementById(targetId);
    if (!target) return;
    const observer = new IntersectionObserver(([entry]) => {
      setVisible(!entry.isIntersecting);
    });
    observer.observe(target);
    return () => observer.disconnect();
  }, [targetId]);

  if (!visible) return null;
  return <button type="button" className="back-to-top-button" onClick={() => {
    const target = document.getElementById(targetId);
    if (!target) return;
    target.focus({ preventScroll: true });
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }}>↑ {label}</button>;
}
