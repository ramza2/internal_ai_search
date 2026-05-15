import React from 'react';
import { Layout } from '../../components/Layout';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { ProgressBar } from '../../components/ProgressBar';
import { Badge } from '../../components/Badge';
import { FileText, CheckCircle, XCircle, Clock, Database, Play, Pause, TestTube } from 'lucide-react';

export function DashboardPage() {
  const stats = {
    totalFiles: 12580,
    analyzedFiles: 11245,
    failedFiles: 235,
    pendingFiles: 1100,
    vectorDBChunks: 45680
  };

  const recentIndexing = {
    status: '진행 중',
    progress: 67,
    currentFile: '/documents/2024/reports/annual_report.pdf',
    processed: 7540,
    failed: 15,
    remaining: 3645
  };

  const recentLogs = [
    { id: 1, time: '2024-12-15 14:30', user: '홍길동', action: '인덱싱 시작', status: 'success' },
    { id: 2, time: '2024-12-15 13:15', user: '김영희', action: 'ownCloud 설정 변경', status: 'success' },
    { id: 3, time: '2024-12-15 12:00', user: '박철수', action: '사용자 승인', status: 'success' },
    { id: 4, time: '2024-12-15 11:45', user: '이민수', action: '제외 정책 수정', status: 'success' },
    { id: 5, time: '2024-12-15 10:30', user: '정수진', action: '파일 분석 실패', status: 'error' }
  ];

  return (
    <Layout>
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl text-gray-900 mb-2">관리자 대시보드</h1>
          <p className="text-sm text-gray-600">시스템 전체 현황을 확인하세요</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
          <Card padding="md">
            <div className="flex items-center gap-3 mb-2">
              <FileText className="w-6 h-6 text-blue-600" />
              <span className="text-sm text-gray-600">전체 파일</span>
            </div>
            <p className="text-2xl text-gray-900">{stats.totalFiles.toLocaleString()}</p>
          </Card>

          <Card padding="md">
            <div className="flex items-center gap-3 mb-2">
              <CheckCircle className="w-6 h-6 text-green-600" />
              <span className="text-sm text-gray-600">분석 완료</span>
            </div>
            <p className="text-2xl text-gray-900">{stats.analyzedFiles.toLocaleString()}</p>
          </Card>

          <Card padding="md">
            <div className="flex items-center gap-3 mb-2">
              <XCircle className="w-6 h-6 text-red-600" />
              <span className="text-sm text-gray-600">분석 실패</span>
            </div>
            <p className="text-2xl text-gray-900">{stats.failedFiles.toLocaleString()}</p>
          </Card>

          <Card padding="md">
            <div className="flex items-center gap-3 mb-2">
              <Clock className="w-6 h-6 text-yellow-600" />
              <span className="text-sm text-gray-600">대기 중</span>
            </div>
            <p className="text-2xl text-gray-900">{stats.pendingFiles.toLocaleString()}</p>
          </Card>

          <Card padding="md">
            <div className="flex items-center gap-3 mb-2">
              <Database className="w-6 h-6 text-purple-600" />
              <span className="text-sm text-gray-600">Vector DB</span>
            </div>
            <p className="text-2xl text-gray-900">{stats.vectorDBChunks.toLocaleString()}</p>
          </Card>
        </div>

        <Card className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg text-gray-900">최근 인덱싱 상태</h2>
            <Badge variant="warning">{recentIndexing.status}</Badge>
          </div>

          <div className="mb-4">
            <ProgressBar
              value={recentIndexing.progress}
              max={100}
              showLabel
              variant="primary"
              size="lg"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div className="bg-gray-50 p-3 rounded-lg">
              <span className="text-xs text-gray-600">처리 완료</span>
              <p className="text-lg text-gray-900">{recentIndexing.processed.toLocaleString()}</p>
            </div>
            <div className="bg-gray-50 p-3 rounded-lg">
              <span className="text-xs text-gray-600">실패</span>
              <p className="text-lg text-red-600">{recentIndexing.failed.toLocaleString()}</p>
            </div>
            <div className="bg-gray-50 p-3 rounded-lg">
              <span className="text-xs text-gray-600">남은 수</span>
              <p className="text-lg text-gray-900">{recentIndexing.remaining.toLocaleString()}</p>
            </div>
          </div>

          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4">
            <p className="text-sm text-blue-800">
              <strong>현재 분석 중:</strong> {recentIndexing.currentFile}
            </p>
          </div>

          <div className="grid grid-cols-2 lg:flex gap-2 lg:gap-3">
            <Button variant="primary" className="text-sm">
              <Play className="w-4 h-4" />
              <span className="hidden sm:inline">전체 분석 시작</span>
              <span className="sm:hidden">전체 분석</span>
            </Button>
            <Button variant="outline" className="text-sm">
              <Play className="w-4 h-4" />
              <span className="hidden sm:inline">변경분 분석</span>
              <span className="sm:hidden">변경분</span>
            </Button>
            <Button variant="danger" className="text-sm">
              <Pause className="w-4 h-4" />
              <span className="hidden sm:inline">분석 중지</span>
              <span className="sm:hidden">중지</span>
            </Button>
            <Button variant="secondary" className="text-sm">
              <TestTube className="w-4 h-4" />
              <span className="hidden sm:inline">데이터 소스 테스트</span>
              <span className="sm:hidden">테스트</span>
            </Button>
          </div>
        </Card>

        <Card>
          <h2 className="text-lg text-gray-900 mb-4">최근 관리자 작업 로그</h2>
          <div className="space-y-2">
            {recentLogs.map((log) => (
              <div
                key={log.id}
                className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 p-3 bg-gray-50 rounded-lg border border-gray-200"
              >
                <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
                  <span className="text-xs sm:text-sm text-gray-600">{log.time}</span>
                  <span className="text-xs sm:text-sm text-gray-900">{log.user}</span>
                  <span className="text-xs sm:text-sm text-gray-700">{log.action}</span>
                </div>
                <Badge variant={log.status === 'success' ? 'success' : 'danger'} className="self-start sm:self-auto">
                  {log.status === 'success' ? '성공' : '실패'}
                </Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </Layout>
  );
}
