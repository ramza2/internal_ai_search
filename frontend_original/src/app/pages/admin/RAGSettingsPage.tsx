import React, { useState } from 'react';
import { Layout } from '../../components/Layout';
import { Card } from '../../components/Card';
import { Input } from '../../components/Input';
import { Select } from '../../components/Select';
import { Button } from '../../components/Button';
import { AlertCircle } from 'lucide-react';

export function RAGSettingsPage() {
  const [settings, setSettings] = useState({
    embeddingModel: 'text-embedding-ada-002',
    llmModel: 'gpt-4',
    chunkSize: '1000',
    chunkOverlap: '200',
    searchResultCount: '5',
    generateAnswer: true,
    enforceSource: true,
    limitUnfoundedAnswer: true
  });

  const handleSave = () => {
    alert('RAG/LLM 설정이 저장되었습니다.');
  };

  return (
    <Layout>
      <div className="max-w-4xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl text-gray-900 mb-2">RAG/LLM 설정</h1>
          <p className="text-sm text-gray-600">AI 검색 및 답변 생성을 위한 설정을 관리하세요</p>
        </div>

        <Card className="mb-6">
          <h2 className="text-lg text-gray-900 mb-4">모델 설정</h2>
          <div className="space-y-4">
            <Select
              label="임베딩 모델"
              value={settings.embeddingModel}
              onChange={(e) => setSettings({ ...settings, embeddingModel: e.target.value })}
              options={[
                { value: 'text-embedding-ada-002', label: 'OpenAI text-embedding-ada-002' },
                { value: 'text-embedding-3-small', label: 'OpenAI text-embedding-3-small' },
                { value: 'text-embedding-3-large', label: 'OpenAI text-embedding-3-large' }
              ]}
            />

            <Select
              label="LLM 모델"
              value={settings.llmModel}
              onChange={(e) => setSettings({ ...settings, llmModel: e.target.value })}
              options={[
                { value: 'gpt-4', label: 'OpenAI GPT-4' },
                { value: 'gpt-4-turbo', label: 'OpenAI GPT-4 Turbo' },
                { value: 'gpt-3.5-turbo', label: 'OpenAI GPT-3.5 Turbo' }
              ]}
            />
          </div>
        </Card>

        <Card className="mb-6">
          <h2 className="text-lg text-gray-900 mb-4">Chunk 설정</h2>
          <div className="space-y-4">
            <Input
              label="Chunk 크기"
              type="number"
              value={settings.chunkSize}
              onChange={(e) => setSettings({ ...settings, chunkSize: e.target.value })}
              helperText="텍스트를 분할할 chunk의 최대 문자 수 (권장: 500-2000)"
            />

            <Input
              label="Chunk Overlap"
              type="number"
              value={settings.chunkOverlap}
              onChange={(e) => setSettings({ ...settings, chunkOverlap: e.target.value })}
              helperText="인접한 chunk 간 겹치는 문자 수 (권장: chunk 크기의 10-20%)"
            />
          </div>
        </Card>

        <Card className="mb-6">
          <h2 className="text-lg text-gray-900 mb-4">검색 및 답변 설정</h2>
          <div className="space-y-4">
            <Input
              label="검색 결과 개수"
              type="number"
              value={settings.searchResultCount}
              onChange={(e) => setSettings({ ...settings, searchResultCount: e.target.value })}
              helperText="Vector DB에서 검색할 최대 chunk 개수 (권장: 3-10)"
            />

            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div>
                <p className="text-sm text-gray-900">답변 생성 여부</p>
                <p className="text-xs text-gray-600">검색 결과를 바탕으로 AI 답변을 생성합니다</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.generateAnswer}
                  onChange={(e) => setSettings({ ...settings, generateAnswer: e.target.checked })}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>

            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div>
                <p className="text-sm text-gray-900">출처 표시 강제</p>
                <p className="text-xs text-gray-600">답변 시 반드시 출처 문서를 함께 표시합니다</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.enforceSource}
                  onChange={(e) => setSettings({ ...settings, enforceSource: e.target.checked })}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>

            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div>
                <p className="text-sm text-gray-900">근거 부족 시 답변 제한</p>
                <p className="text-xs text-gray-600">검색된 문서에 근거가 부족하면 답변하지 않습니다</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.limitUnfoundedAnswer}
                  onChange={(e) => setSettings({ ...settings, limitUnfoundedAnswer: e.target.checked })}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>
          </div>
        </Card>

        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6 flex gap-3">
          <AlertCircle className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-blue-800">
            <p className="mb-1">설정 변경 시 유의사항:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>임베딩 모델 변경 시 전체 재인덱싱이 필요합니다</li>
              <li>Chunk 크기 변경 시 기존 chunk는 자동으로 재생성됩니다</li>
              <li>LLM 모델 변경은 즉시 적용됩니다</li>
            </ul>
          </div>
        </div>

        <div className="flex gap-3">
          <Button variant="primary" onClick={handleSave}>
            설정 저장
          </Button>
          <Button variant="outline">
            기본값으로 초기화
          </Button>
        </div>
      </div>
    </Layout>
  );
}
