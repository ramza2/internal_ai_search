import React from 'react';
import { useParams } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { Badge } from '../components/Badge';
import { ExternalLink, Copy, Download, FileText, Calendar, HardDrive } from 'lucide-react';

export function FileDetailPage() {
  const { id } = useParams();

  const mockFile = {
    id: id,
    fileName: 'product_spec_v2.pdf',
    filePath: '/documents/products/2024/product_spec_v2.pdf',
    dataSource: '사내 문서함',
    dataSourceType: 'ownCloud',
    serverUrl: 'https://cloud.company.com',
    webdavRootPath: '/remote.php/dav/files/admin',
    remoteFilePath: '/remote.php/dav/files/admin/documents/products/2024/product_spec_v2.pdf',
    extension: 'pdf',
    fileSize: '2.4 MB',
    modifiedDate: '2024-12-15 14:30:25',
    analysisStatus: '분석 완료',
    etag: 'abc123def456',
    content: `제품 사양서 v2.0

1. 개요
본 문서는 2024년 신제품의 기술 사양을 정의합니다.

2. 주요 사양
- 메모리: 16GB DDR5
- 저장 장치: 512GB NVMe SSD
- 프로세서: Intel Core i7-13700K
- 그래픽: NVIDIA RTX 4070

3. 변경 이력
- 2024-12-15: 메모리 용량 8GB → 16GB 증가
- 2024-12-15: 배터리 수명 개선 (8시간 → 12시간)

4. 승인
제품 기획팀 승인 완료`,
    chunks: [
      { id: 1, chunkNumber: 1, content: '제품 사양서 v2.0\n\n1. 개요\n본 문서는 2024년 신제품의 기술 사양을 정의합니다.' },
      { id: 2, chunkNumber: 2, content: '2. 주요 사양\n- 메모리: 16GB DDR5\n- 저장 장치: 512GB NVMe SSD' },
      { id: 3, chunkNumber: 3, content: '- 프로세서: Intel Core i7-13700K\n- 그래픽: NVIDIA RTX 4070' },
      { id: 4, chunkNumber: 4, content: '3. 변경 이력\n- 2024-12-15: 메모리 용량 8GB → 16GB 증가' }
    ]
  };

  return (
    <Layout>
      <div className="max-w-5xl mx-auto">
        <div className="mb-6">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-3">
              <Badge variant="info">{mockFile.dataSource}</Badge>
              <h1 className="text-2xl text-gray-900">{mockFile.fileName}</h1>
            </div>
            <Badge variant="success">{mockFile.analysisStatus}</Badge>
          </div>
          <p className="text-sm text-gray-600">{mockFile.filePath}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
          <Card>
            <div className="flex items-center gap-3 mb-2">
              <FileText className="w-5 h-5 text-blue-600" />
              <span className="text-sm text-gray-600">확장자</span>
            </div>
            <p className="text-lg text-gray-900">{mockFile.extension.toUpperCase()}</p>
          </Card>

          <Card>
            <div className="flex items-center gap-3 mb-2">
              <HardDrive className="w-5 h-5 text-blue-600" />
              <span className="text-sm text-gray-600">파일 크기</span>
            </div>
            <p className="text-lg text-gray-900">{mockFile.fileSize}</p>
          </Card>

          <Card>
            <div className="flex items-center gap-3 mb-2">
              <Calendar className="w-5 h-5 text-blue-600" />
              <span className="text-sm text-gray-600">수정일</span>
            </div>
            <p className="text-lg text-gray-900">{mockFile.modifiedDate}</p>
          </Card>
        </div>

        <Card className="mb-6">
          <h2 className="text-lg text-gray-900 mb-4">데이터 소스 정보</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <span className="text-sm text-gray-600">데이터 소스명</span>
              <p className="text-sm text-gray-900 mt-1">{mockFile.dataSource}</p>
            </div>
            <div>
              <span className="text-sm text-gray-600">데이터 소스 유형</span>
              <p className="text-sm text-gray-900 mt-1">{mockFile.dataSourceType}</p>
            </div>
            <div>
              <span className="text-sm text-gray-600">서버 URL</span>
              <p className="text-sm text-gray-900 mt-1">{mockFile.serverUrl}</p>
            </div>
            <div>
              <span className="text-sm text-gray-600">WebDAV 루트 경로</span>
              <p className="text-sm text-gray-900 mt-1 font-mono">{mockFile.webdavRootPath}</p>
            </div>
          </div>

          <h2 className="text-lg text-gray-900 mb-4 mt-6">파일 정보</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <span className="text-sm text-gray-600">파일 원격 경로</span>
              <p className="text-sm text-gray-900 mt-1 font-mono">{mockFile.remoteFilePath}</p>
            </div>
            <div>
              <span className="text-sm text-gray-600">로컬 경로</span>
              <p className="text-sm text-gray-900 mt-1">{mockFile.filePath}</p>
            </div>
            <div>
              <span className="text-sm text-gray-600">ETag</span>
              <p className="text-sm text-gray-900 mt-1 font-mono">{mockFile.etag}</p>
            </div>
          </div>

          <div className="mt-6 flex gap-3">
            <Button variant="primary">
              <ExternalLink className="w-4 h-4" />
              원본 저장소에서 열기
            </Button>
            <Button variant="outline">
              <Copy className="w-4 h-4" />
              경로 복사
            </Button>
            <Button variant="outline">
              <Download className="w-4 h-4" />
              다운로드
            </Button>
          </div>
        </Card>

        <Card className="mb-6">
          <h2 className="text-lg text-gray-900 mb-4">본문 미리보기</h2>
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
            <pre className="text-sm text-gray-800 whitespace-pre-wrap font-mono">
              {mockFile.content}
            </pre>
          </div>
        </Card>

        <Card>
          <h2 className="text-lg text-gray-900 mb-4">관련 Chunk 목록</h2>
          <p className="text-sm text-gray-600 mb-4">
            Vector DB에 저장된 {mockFile.chunks.length}개의 청크
          </p>
          <div className="space-y-3">
            {mockFile.chunks.map((chunk) => (
              <div key={chunk.id} className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Badge variant="info" size="sm">Chunk {chunk.chunkNumber}</Badge>
                </div>
                <p className="text-sm text-gray-700">{chunk.content}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </Layout>
  );
}
