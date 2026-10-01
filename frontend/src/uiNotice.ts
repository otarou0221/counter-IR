export type NoticeTone = "info" | "success" | "warning" | "error";

export type UiNotice = {
  message: string;
  tone: NoticeTone;
};

export type NoticeHandler = (message: string, tone?: NoticeTone) => void;
