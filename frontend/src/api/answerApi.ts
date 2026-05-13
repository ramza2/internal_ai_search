import { httpClient } from "@/api/httpClient";
import type { AnswerRequest, AnswerResponse } from "@/types/answer";

export async function answerRequest(body: AnswerRequest): Promise<AnswerResponse> {
  const { data } = await httpClient.post<AnswerResponse>("/api/answer", body);
  return data;
}
