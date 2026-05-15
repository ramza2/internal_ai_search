import React, { useState } from 'react';
import { Layout } from '../../components/Layout';
import { Card } from '../../components/Card';
import { Table } from '../../components/Table';
import { Button } from '../../components/Button';
import { Badge } from '../../components/Badge';
import { Select } from '../../components/Select';
import { Input } from '../../components/Input';
import { Download } from 'lucide-react';

export function LogsPage() {
  const [startDate, setStartDate] = useState('2024-12-01');
  const [endDate, setEndDate] = useState('2024-12-15');
  const [userFilter, setUserFilter] = useState('all');
  const [actionFilter, setActionFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  const logsData = [
    {
      id: 1,
      timestamp: '2024-12-15 14:30:25',
      user: '홍길동',
      role: '관리자',
      action: 'INDEX_START',
      actionLabel: '인덱싱 시작',
      target: '전체 분석',
      url: '/api/admin/indexing/start',
      ip: '192.168.1.100',
      success: true
    },
    {
      id: 2,
      timestamp: '2024-12-15 13:15:42',
      user: '김영희',
      role: '일반 사용자',
      action: 'SEARCH',
      actionLabel: '검색',
      target: 'api documentation',
      url: '/api/search',
      ip: '192.168.1.101',
      success: true
    },
    {
      id: 3,
      timestamp: '2024-12-15 12:05:18',
      user: '박철수',
      role: '관리자',
      action: 'USER_UPDATE',
      actionLabel: '사용자 수정',
      target: 'kim (승인)',
      url: '/api/admin/users/2',
      ip: '192.168.1.102',
      success: true
    },
    {
      id: 4,
      timestamp: '2024-12-15 11:45:33',
      user: '이민수',
      role: '일반 사용자',
      action: 'FILE_VIEW',
      actionLabel: '파일 조회',
      target: '/documents/spec.pdf',
      url: '/api/files/123',
      ip: '192.168.1.103',
      success: true
    },
    {
      id: 5,
      timestamp: '2024-12-15 10:30:15',
      user: '정수진',
      role: '일반 사용자',
      action: 'LOGIN',
      actionLabel: '로그인',
      target: '-',
      url: '/api/auth/login',
      ip: '192.168.1.104',
      success: true
    },
    {
      id: 6,
      timestamp: '2024-12-15 09:22:47',
      user: 'unknown',
      role: '-',
      action: 'ERROR',
      actionLabel: '오류',
      target: 'Authentication failed',
      url: '/api/auth/login',
      ip: '192.168.1.200',
      success: false
    }
  ];

  const columns = [
    { key: 'timestamp', header: '시간', width: '160px' },
    { key: 'user', header: '사용자' },
    {
      key: 'role',
      header: '권한',
      render: (value: string) => (
        value !== '-' ? <Badge variant={value === '관리자' ? 'primary' : 'info'} size="sm">{value}</Badge> : '-'
      )
    },
    {
      key: 'actionLabel',
      header: '작업 종류',
      render: (value: string, row: any) => {
        const colors: { [key: string]: 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'gray' } = {
          LOGIN: 'success',
          LOGOUT: 'gray',
          SEARCH: 'info',
          FILE_VIEW: 'info',
          INDEX_START: 'primary',
          USER_UPDATE: 'warning',
          ERROR: 'danger'
        };
        return <Badge variant={colors[row.action] || 'gray'} size="sm">{value}</Badge>;
      }
    },
    { key: 'target', header: '대상' },
    { key: 'url', header: '요청 URL', width: '200px' },
    { key: 'ip', header: 'IP 주소', width: '120px' },
    {
      key: 'success',
      header: '성공 여부',
      render: (value: boolean) => (
        <Badge variant={value ? 'success' : 'danger'} size="sm">
          {value ? '성공' : '실패'}
        </Badge>
      )
    }
  ];

  const handleExport = () => {
    alert('CSV 파일이 다운로드됩니다.');
  };

  return (
    <Layout>
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl text-gray-900 mb-2">작업 로그 조회</h1>
          <p className="text-sm text-gray-600">모든 사용자 작업을 조회하고 추적하세요</p>
        </div>

        <Card className="mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
            <Input
              label="시작일"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
            <Input
              label="종료일"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
            <Select
              label="사용자"
              value={userFilter}
              onChange={(e) => setUserFilter(e.target.value)}
              options={[
                { value: 'all', label: '전체' },
                { value: 'hong', label: '홍길동' },
                { value: 'kim', label: '김영희' },
                { value: 'park', label: '박철수' }
              ]}
            />
            <Select
              label="작업 종류"
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              options={[
                { value: 'all', label: '전체' },
                { value: 'LOGIN', label: '로그인' },
                { value: 'SEARCH', label: '검색' },
                { value: 'FILE_VIEW', label: '파일 조회' },
                { value: 'INDEX_START', label: '인덱싱' },
                { value: 'USER_UPDATE', label: '사용자 수정' },
                { value: 'ERROR', label: '오류' }
              ]}
            />
          </div>
          <Input
            label="검색어"
            placeholder="대상, URL, IP 주소 검색"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </Card>

        <Card>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg text-gray-900">로그 목록 ({logsData.length}개)</h2>
            <Button variant="outline" onClick={handleExport}>
              <Download className="w-4 h-4" />
              CSV 다운로드
            </Button>
          </div>
          <Table columns={columns} data={logsData} />
        </Card>
      </div>
    </Layout>
  );
}
