import type { FileTypeBucket } from "@/types/search";

export const FILE_TYPE_FILTER_OPTIONS: { value: "" | FileTypeBucket; label: string }[] = [
  { value: "", label: "전체" },
  { value: "DOCUMENT", label: "DOCUMENT" },
  { value: "SOURCE_CODE", label: "SOURCE_CODE" },
  { value: "CONFIG", label: "CONFIG" },
  { value: "LOG", label: "LOG" },
  { value: "IMAGE", label: "IMAGE" },
  { value: "AUDIO_VIDEO", label: "AUDIO_VIDEO" },
  { value: "ARCHIVE", label: "ARCHIVE" },
  { value: "BINARY", label: "BINARY" },
  { value: "UNKNOWN", label: "UNKNOWN" },
];

/** 작업 로그 action_type 빠른 선택 (자유 입력도 가능하도록 별도 필드와 병행 가능) */
export const COMMON_ACTION_TYPES: string[] = [
  "",
  "SEARCH",
  "RAG_QUESTION",
  "FILE_PREVIEW",
  "LOGIN",
  "LOGIN_FAILED",
  "SIGNUP",
  "PASSWORD_CHANGE",
  "ACTION_LOG_VIEW",
  "USER_APPROVE",
  "USER_ACTIVATE",
  "USER_DEACTIVATE",
  "USER_LOCK",
  "USER_ROLE_CHANGE",
  "DATA_SOURCE_CREATE",
  "DATA_SOURCE_UPDATE",
  "DATA_SOURCE_ACTIVATE",
  "DATA_SOURCE_DEACTIVATE",
  "DATA_SOURCE_TEST_CONNECTION",
];
