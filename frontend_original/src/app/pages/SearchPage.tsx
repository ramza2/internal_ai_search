import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { Card } from '../components/Card';
import { SearchInput } from '../components/SearchInput';
import { Button } from '../components/Button';
import { Badge } from '../components/Badge';
import { Select } from '../components/Select';
import { Input } from '../components/Input';
import { ChevronDown, FileText, ExternalLink, Copy, Calendar } from 'lucide-react';

export function SearchPage() {
  const navigate = useNavigate();
  const [showFilters, setShowFilters] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const mockResults = [
    {
      id: 1,
      fileName: 'product_spec_v2.pdf',
      filePath: '/documents/products/2024/product_spec_v2.pdf',
      extension: 'pdf',
      modifiedDate: '2024-12-15',
      relevanceScore: 95,
      searchLocation: '본문',
      dataSource: '사내 문서함',
      preview: '제품 사양서 업데이트 내용... 주요 변경사항은 메모리 용량 증가 및 배터리 수명 개선...'
    },
    {
      id: 2,
      fileName: 'api_documentation.md',
      filePath: '/code/backend/docs/api_documentation.md',
      extension: 'md',
      modifiedDate: '2024-12-10',
      relevanceScore: 88,
      searchLocation: '파일명',
      dataSource: '사내 문서함',
      preview: 'REST API 엔드포인트 목록 및 사용 예제. GET /api/users - 사용자 목록 조회...'
    },
    {
      id: 3,
      fileName: 'UserService.java',
      filePath: '/code/backend/src/service/UserService.java',
      extension: 'java',
      modifiedDate: '2024-12-08',
      relevanceScore: 82,
      searchLocation: '코드',
      dataSource: '고객사 A WebDAV',
      preview: 'public class UserService { public User findById(Long id) { return userRepository.findById(id); } }'
    }
  ];

  const extensionColor: { [key: string]: 'primary' | 'success' | 'warning' | 'danger' | 'info' } = {
    pdf: 'danger',
    md: 'info',
    java: 'warning',
    py: 'success',
    js: 'warning'
  };

  return (
    <Layout>
      <div className="max-w-6xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl text-gray-900 mb-2">통합 검색</h1>
          <p className="text-sm text-gray-600">사내 ownCloud의 문서와 소스 파일을 검색하세요</p>
        </div>

        <Card className="mb-6">
          <div className="space-y-4">
            <div className="flex gap-3">
              <SearchInput
                placeholder="파일명, 경로, 본문, 코드 내용 검색..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex-1"
              />
              <Button variant="primary" className="px-8">
                검색
              </Button>
            </div>

            <button
              onClick={() => setShowFilters(!showFilters)}
              className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-700"
            >
              <ChevronDown className={`w-4 h-4 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
              고급 필터 {showFilters ? '숨기기' : '표시'}
            </button>

            {showFilters && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-4 border-t border-gray-200">
                <Select
                  label="데이터 소스"
                  options={[
                    { value: 'all', label: '전체' },
                    { value: 'internal', label: '사내 문서함' },
                    { value: 'client-a', label: '고객사 A WebDAV' },
                    { value: 'test', label: '테스트 WebDAV' }
                  ]}
                />
                <Input label="확장자" placeholder="예: pdf, docx, java" />
                <Select
                  label="문서 유형"
                  options={[
                    { value: 'all', label: '전체' },
                    { value: 'document', label: '문서' },
                    { value: 'code', label: '소스 코드' },
                    { value: 'image', label: '이미지' },
                    { value: 'archive', label: '압축 파일' }
                  ]}
                />
                <Input label="파일 경로" placeholder="예: /documents/2024" />
                <Input label="수정일 (시작)" type="date" />
                <Input label="수정일 (종료)" type="date" />
                <Select
                  label="파일 크기"
                  options={[
                    { value: 'all', label: '전체' },
                    { value: 'small', label: '1MB 이하' },
                    { value: 'medium', label: '1MB - 10MB' },
                    { value: 'large', label: '10MB - 100MB' },
                    { value: 'xlarge', label: '100MB 이상' }
                  ]}
                />
              </div>
            )}
          </div>
        </Card>

        <div className="space-y-4">
          {searchQuery && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-600">총 {mockResults.length}개의 검색 결과</p>
            </div>
          )}

          {mockResults.map((result) => (
            <Card key={result.id} padding="md" hover>
              <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <FileText className="w-5 h-5 text-gray-400 flex-shrink-0" />
                    <Badge variant="info" size="sm">
                      {result.dataSource}
                    </Badge>
                    <h3
                      className="text-base lg:text-lg text-blue-600 hover:text-blue-700 cursor-pointer break-all"
                      onClick={() => navigate(`/file/${result.id}`)}
                    >
                      {result.fileName}
                    </h3>
                    <Badge variant={extensionColor[result.extension] || 'gray'}>
                      {result.extension.toUpperCase()}
                    </Badge>
                    <span className="text-xs lg:text-sm text-gray-500">관련도: {result.relevanceScore}%</span>
                  </div>

                  <p className="text-xs lg:text-sm text-gray-600 mb-2 break-all">{result.filePath}</p>

                  <div className="flex flex-wrap items-center gap-2 lg:gap-4 mb-3 text-xs lg:text-sm text-gray-500">
                    <span className="flex items-center gap-1">
                      <Calendar className="w-4 h-4" />
                      {result.modifiedDate}
                    </span>
                    <Badge variant="info" size="sm">
                      검색 위치: {result.searchLocation}
                    </Badge>
                  </div>

                  <p className="text-xs lg:text-sm text-gray-700 bg-gray-50 p-3 rounded-lg border border-gray-200">
                    {result.preview}
                  </p>
                </div>

                <div className="flex flex-row lg:flex-col gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate(`/file/${result.id}`)}
                    className="flex-1 lg:flex-none"
                  >
                    상세 보기
                  </Button>
                  <Button variant="ghost" size="sm" className="flex-1 lg:flex-none">
                    <Copy className="w-4 h-4" />
                    <span className="lg:hidden">복사</span>
                    <span className="hidden lg:inline">경로 복사</span>
                  </Button>
                  <Button variant="ghost" size="sm" className="flex-1 lg:flex-none">
                    <ExternalLink className="w-4 h-4" />
                    <span className="lg:hidden">원본</span>
                    <span className="hidden lg:inline">원본 저장소</span>
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </Layout>
  );
}
