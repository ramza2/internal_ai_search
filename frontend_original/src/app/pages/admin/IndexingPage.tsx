import React, { useState } from 'react';
import { Layout } from '../../components/Layout';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { ProgressBar } from '../../components/ProgressBar';
import { Badge } from '../../components/Badge';
import { Table } from '../../components/Table';
import { Select } from '../../components/Select';
import { Play, Pause, RefreshCw, Calendar } from 'lucide-react';

export function IndexingPage() {
  const [isRunning, setIsRunning] = useState(true);
  const [selectedDataSource, setSelectedDataSource] = useState('all');

  const currentStatus = {
    status: isRunning ? '진행 중' : '중지됨',
    progress: 67,
    currentFile: '/documents/2024/reports/annual_report.pdf',
    processed: 7540,
    failed: 15,
    remaining: 3645
  };

  const scheduleSettings = {
    dailyIncremental: true,
    weeklyFull: true,
    dailyTime: '02:00',
    weeklyDay: '일요일'
  };

  const historyData = [
    {
      id: 1,
      dataSource: '사내 문서함',
      startTime: '2024-12-15 02:00:00',
      endTime: '2024-12-15 04:30:15',
      type: '변경분 분석',
      totalFiles: 3200,
      processed: 3185,
      failed: 15,
      status: '완료'
    },
    {
      id: 2,
      dataSource: '고객사 A WebDAV',
      startTime: '2024-12-14 02:00:00',
      endTime: '2024-12-14 04:15:30',
      type: '변경분 분석',
      totalFiles: 2890,
      processed: 2890,
      failed: 0,
      status: '완료'
    },
    {
      id: 3,
      dataSource: '사내 문서함',
      startTime: '2024-12-08 02:00:00',
      endTime: '2024-12-08 08:45:20',
      type: '전체 재검증',
      totalFiles: 12580,
      processed: 12345,
      failed: 235,
      status: '완료'
    }
  ];

  const columns = [
    {
      key: 'dataSource',
      header: '데이터 소스',
      render: (value: string) => <Badge variant="info" size="sm">{value}</Badge>
    },
    { key: 'startTime', header: '시작 시간' },
    { key: 'endTime', header: '종료 시간' },
    {
      key: 'type',
      header: '분석 유형',
      render: (value: string) => (
        <Badge variant={value === '전체 재검증' ? 'primary' : 'info'}>{value}</Badge>
      )
    },
    { key: 'totalFiles', header: '전체 파일', render: (value: number) => value.toLocaleString() },
    { key: 'processed', header: '처리 완료', render: (value: number) => value.toLocaleString() },
    {
      key: 'failed',
      header: '실패',
      render: (value: number) => (
        <span className={value > 0 ? 'text-red-600' : 'text-gray-900'}>
          {value.toLocaleString()}
        </span>
      )
    },
    {
      key: 'status',
      header: '상태',
      render: (value: string) => <Badge variant="success">{value}</Badge>
    }
  ];

  return (
    <Layout>
      <div className="max-w-6xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl text-gray-900 mb-2">인덱싱 관리</h1>
          <p className="text-sm text-gray-600">파일 분석 및 인덱싱 작업을 관리하세요</p>
        </div>

        <Card className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg text-gray-900">현재 분석 상태</h2>
            <div className="flex items-center gap-3">
              <Select
                value={selectedDataSource}
                onChange={(e) => setSelectedDataSource(e.target.value)}
                options={[
                  { value: 'all', label: '전체 데이터 소스' },
                  { value: 'internal', label: '사내 문서함' },
                  { value: 'client-a', label: '고객사 A WebDAV' },
                  { value: 'test', label: '테스트 WebDAV' }
                ]}
              />
              <Badge variant={isRunning ? 'warning' : 'gray'}>{currentStatus.status}</Badge>
            </div>
          </div>

          <div className="mb-4">
            <ProgressBar
              value={currentStatus.progress}
              max={100}
              showLabel
              variant="primary"
              size="lg"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div className="bg-gray-50 p-3 rounded-lg">
              <span className="text-xs text-gray-600">처리 완료</span>
              <p className="text-lg text-gray-900">{currentStatus.processed.toLocaleString()}</p>
            </div>
            <div className="bg-gray-50 p-3 rounded-lg">
              <span className="text-xs text-gray-600">실패</span>
              <p className="text-lg text-red-600">{currentStatus.failed.toLocaleString()}</p>
            </div>
            <div className="bg-gray-50 p-3 rounded-lg">
              <span className="text-xs text-gray-600">남은 수</span>
              <p className="text-lg text-gray-900">{currentStatus.remaining.toLocaleString()}</p>
            </div>
          </div>

          {isRunning && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4">
              <p className="text-sm text-blue-800">
                <strong>현재 분석 중:</strong> {currentStatus.currentFile}
              </p>
            </div>
          )}

          <div className="flex gap-3">
            <Button variant="primary" onClick={() => setIsRunning(true)}>
              <Play className="w-4 h-4" />
              전체 분석 시작
            </Button>
            <Button variant="outline" onClick={() => setIsRunning(true)}>
              <RefreshCw className="w-4 h-4" />
              변경분 분석
            </Button>
            <Button variant="danger" onClick={() => setIsRunning(false)}>
              <Pause className="w-4 h-4" />
              중지
            </Button>
            <Button variant="secondary">
              <RefreshCw className="w-4 h-4" />
              재시작
            </Button>
          </div>
        </Card>

        <Card className="mb-6">
          <h2 className="text-lg text-gray-900 mb-4">스케줄 분석 설정</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-3">
                <Calendar className="w-5 h-5 text-blue-600" />
                <div>
                  <p className="text-sm text-gray-900">매일 새벽 변경분 분석</p>
                  <p className="text-xs text-gray-600">실행 시간: {scheduleSettings.dailyTime}</p>
                </div>
              </div>
              <Badge variant={scheduleSettings.dailyIncremental ? 'success' : 'gray'}>
                {scheduleSettings.dailyIncremental ? '활성화' : '비활성화'}
              </Badge>
            </div>

            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-3">
                <Calendar className="w-5 h-5 text-blue-600" />
                <div>
                  <p className="text-sm text-gray-900">주 1회 전체 재검증</p>
                  <p className="text-xs text-gray-600">실행 요일: {scheduleSettings.weeklyDay}</p>
                </div>
              </div>
              <Badge variant={scheduleSettings.weeklyFull ? 'success' : 'gray'}>
                {scheduleSettings.weeklyFull ? '활성화' : '비활성화'}
              </Badge>
            </div>
          </div>

          <div className="mt-4">
            <Button variant="outline">스케줄 설정 변경</Button>
          </div>
        </Card>

        <Card>
          <h2 className="text-lg text-gray-900 mb-4">최근 분석 이력</h2>
          <Table columns={columns} data={historyData} />
        </Card>
      </div>
    </Layout>
  );
}
