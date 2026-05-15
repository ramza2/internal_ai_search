import React, { useState } from 'react';
import { Layout } from '../../components/Layout';
import { Card } from '../../components/Card';
import { Table } from '../../components/Table';
import { Button } from '../../components/Button';
import { Badge } from '../../components/Badge';
import { Select } from '../../components/Select';
import { RefreshCw, X } from 'lucide-react';

export function FailedFilesPage() {
  const [reasonFilter, setReasonFilter] = useState('all');
  const [extensionFilter, setExtensionFilter] = useState('all');

  const failedFilesData = [
    {
      id: 1,
      fileName: 'protected_document.pdf',
      filePath: '/documents/confidential/protected_document.pdf',
      extension: 'pdf',
      reason: 'PASSWORD_PROTECTED',
      reasonLabel: '비밀번호 보호',
      lastAttempt: '2024-12-15 14:30:25',
      attemptCount: 3
    },
    {
      id: 2,
      fileName: 'large_video.mp4',
      filePath: '/media/videos/large_video.mp4',
      extension: 'mp4',
      reason: 'FILE_TOO_LARGE',
      reasonLabel: '파일 크기 초과',
      lastAttempt: '2024-12-15 13:15:42',
      attemptCount: 1
    },
    {
      id: 3,
      fileName: 'corrupted_file.docx',
      filePath: '/documents/2024/corrupted_file.docx',
      extension: 'docx',
      reason: 'PARSING_FAILED',
      reasonLabel: '파싱 실패',
      lastAttempt: '2024-12-15 12:05:18',
      attemptCount: 5
    },
    {
      id: 4,
      fileName: 'unknown_format.xyz',
      filePath: '/temp/unknown_format.xyz',
      extension: 'xyz',
      reason: 'UNSUPPORTED_EXTENSION',
      reasonLabel: '지원하지 않는 확장자',
      lastAttempt: '2024-12-15 11:45:33',
      attemptCount: 1
    },
    {
      id: 5,
      fileName: 'broken_encoding.txt',
      filePath: '/documents/old/broken_encoding.txt',
      extension: 'txt',
      reason: 'ENCODING_ERROR',
      reasonLabel: '인코딩 오류',
      lastAttempt: '2024-12-15 10:30:15',
      attemptCount: 2
    },
    {
      id: 6,
      fileName: 'restricted_file.pdf',
      filePath: '/secure/restricted_file.pdf',
      extension: 'pdf',
      reason: 'PERMISSION_DENIED',
      reasonLabel: '권한 없음',
      lastAttempt: '2024-12-15 09:22:47',
      attemptCount: 4
    }
  ];

  const getReasonBadge = (reason: string, reasonLabel: string) => {
    const variants: { [key: string]: 'danger' | 'warning' | 'info' | 'gray' } = {
      'UNSUPPORTED_EXTENSION': 'gray',
      'ENCODING_ERROR': 'warning',
      'FILE_TOO_LARGE': 'info',
      'PASSWORD_PROTECTED': 'danger',
      'DOWNLOAD_FAILED': 'danger',
      'PARSING_FAILED': 'warning',
      'PERMISSION_DENIED': 'danger'
    };
    return <Badge variant={variants[reason] || 'gray'} size="sm">{reasonLabel}</Badge>;
  };

  const columns = [
    { key: 'fileName', header: '파일명', width: '200px' },
    { key: 'filePath', header: '파일 경로', width: '300px' },
    {
      key: 'extension',
      header: '확장자',
      render: (value: string) => <Badge variant="gray" size="sm">{value.toUpperCase()}</Badge>
    },
    {
      key: 'reasonLabel',
      header: '실패 사유',
      render: (_: any, row: any) => getReasonBadge(row.reason, row.reasonLabel)
    },
    { key: 'lastAttempt', header: '마지막 시도', width: '160px' },
    {
      key: 'attemptCount',
      header: '시도 횟수',
      render: (value: number) => (
        <span className={value > 3 ? 'text-red-600' : 'text-gray-900'}>
          {value}회
        </span>
      )
    },
    {
      key: 'actions',
      header: '작업',
      render: () => (
        <div className="flex gap-2">
          <Button variant="outline" size="sm">
            <RefreshCw className="w-4 h-4" />
            재시도
          </Button>
          <Button variant="ghost" size="sm">
            <X className="w-4 h-4" />
            제외
          </Button>
        </div>
      )
    }
  ];

  return (
    <Layout>
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl text-gray-900 mb-2">분석 실패 파일 관리</h1>
          <p className="text-sm text-gray-600">분석에 실패한 파일을 확인하고 재시도하세요</p>
        </div>

        <Card className="mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Select
              label="실패 사유"
              value={reasonFilter}
              onChange={(e) => setReasonFilter(e.target.value)}
              options={[
                { value: 'all', label: '전체' },
                { value: 'UNSUPPORTED_EXTENSION', label: '지원하지 않는 확장자' },
                { value: 'ENCODING_ERROR', label: '인코딩 오류' },
                { value: 'FILE_TOO_LARGE', label: '파일 크기 초과' },
                { value: 'PASSWORD_PROTECTED', label: '비밀번호 보호' },
                { value: 'PARSING_FAILED', label: '파싱 실패' },
                { value: 'PERMISSION_DENIED', label: '권한 없음' }
              ]}
            />
            <Select
              label="확장자"
              value={extensionFilter}
              onChange={(e) => setExtensionFilter(e.target.value)}
              options={[
                { value: 'all', label: '전체' },
                { value: 'pdf', label: 'PDF' },
                { value: 'docx', label: 'DOCX' },
                { value: 'txt', label: 'TXT' },
                { value: 'mp4', label: 'MP4' }
              ]}
            />
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg text-gray-900">실패 파일 목록 ({failedFilesData.length}개)</h2>
            <div className="flex gap-2">
              <Button variant="outline">
                <RefreshCw className="w-4 h-4" />
                전체 재시도
              </Button>
            </div>
          </div>
          <Table columns={columns} data={failedFilesData} />
        </Card>
      </div>
    </Layout>
  );
}
