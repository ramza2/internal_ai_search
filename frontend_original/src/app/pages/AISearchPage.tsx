import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { AlertCircle, FileText, ExternalLink, MessageSquare } from 'lucide-react';
import { Badge } from '../components/Badge';

export function AISearchPage() {
  const navigate = useNavigate();
  const [question, setQuestion] = useState('');
  const [showAnswer, setShowAnswer] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setShowAnswer(true);
  };

  const mockAnswer = {
    answer: '사용자 인증 시스템은 JWT 토큰 기반으로 구현되어 있습니다. 로그인 시 서버에서 JWT 토큰을 발급하며, 클라이언트는 이를 로컬 스토리지에 저장합니다. 이후 API 요청 시 Authorization 헤더에 토큰을 포함하여 전송하고, 서버에서는 미들웨어를 통해 토큰의 유효성을 검증합니다.',
    sources: [
      {
        id: 1,
        fileName: 'AuthService.java',
        filePath: '/code/backend/src/service/AuthService.java',
        location: 'Line 45-78',
        dataSource: '사내 문서함',
        relevance: 95
      },
      {
        id: 2,
        fileName: 'JWT_Implementation.md',
        filePath: '/documents/architecture/JWT_Implementation.md',
        location: 'Page 2-3',
        dataSource: '사내 문서함',
        relevance: 88
      },
      {
        id: 3,
        fileName: 'auth.middleware.ts',
        filePath: '/code/backend/src/middleware/auth.middleware.ts',
        location: 'Chunk 3',
        dataSource: '고객사 A WebDAV',
        relevance: 82
      }
    ]
  };

  return (
    <Layout>
      <div className="max-w-4xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl text-gray-900 mb-2">AI 질문 / RAG 답변</h1>
          <p className="text-sm text-gray-600">사내 문서를 기반으로 AI가 답변합니다</p>
        </div>

        <Card className="mb-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm mb-2 text-gray-700">
                질문을 입력하세요
              </label>
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="예: 사용자 인증 시스템은 어떻게 구현되어 있나요?"
                className="w-full px-4 py-3 border border-gray-300 rounded-lg
                  focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none
                  min-h-[120px] resize-y"
                required
              />
            </div>

            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex gap-3">
              <AlertCircle className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-blue-800">
                <p className="mb-1">AI는 사내 문서를 기반으로만 답변합니다.</p>
                <p>근거가 부족한 경우 답변하지 않습니다.</p>
              </div>
            </div>

            <Button type="submit" variant="primary" className="w-full">
              <MessageSquare className="w-5 h-5" />
              질문하기
            </Button>
          </form>
        </Card>

        {showAnswer && (
          <>
            <Card className="mb-6">
              <div className="mb-4">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-2 h-2 bg-blue-600 rounded-full" />
                  <h2 className="text-lg text-gray-900">AI 답변</h2>
                </div>
                <p className="text-base text-gray-800 leading-relaxed">
                  {mockAnswer.answer}
                </p>
              </div>
            </Card>

            <Card>
              <div className="mb-4">
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-2 h-2 bg-green-600 rounded-full" />
                  <h2 className="text-lg text-gray-900">근거 문서</h2>
                </div>
                <p className="text-sm text-gray-600 mb-4">
                  답변은 다음 {mockAnswer.sources.length}개의 문서를 기반으로 생성되었습니다.
                </p>
              </div>

              <div className="space-y-3">
                {mockAnswer.sources.map((source) => (
                  <div
                    key={source.id}
                    className="flex items-start justify-between gap-4 p-4 bg-gray-50 rounded-lg border border-gray-200 hover:border-blue-300 transition-colors"
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <FileText className="w-4 h-4 text-gray-400" />
                        <Badge variant="info" size="sm">
                          {source.dataSource}
                        </Badge>
                        <h3
                          className="text-sm text-blue-600 hover:text-blue-700 cursor-pointer"
                          onClick={() => navigate(`/file/${source.id}`)}
                        >
                          {source.fileName}
                        </h3>
                      </div>
                      <p className="text-xs text-gray-600 mb-1">{source.filePath}</p>
                      <div className="flex items-center gap-3 text-xs text-gray-500">
                        <span>위치: {source.location}</span>
                        <span>관련도: {source.relevance}%</span>
                      </div>
                    </div>
                    <div className="flex flex-col gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate(`/file/${source.id}`)}
                      >
                        상세 보기
                      </Button>
                      <Button variant="ghost" size="sm">
                        <ExternalLink className="w-4 h-4" />
                        원본 저장소
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </>
        )}
      </div>
    </Layout>
  );
}
