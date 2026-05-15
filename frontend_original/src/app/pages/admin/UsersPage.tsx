import React, { useState } from 'react';
import { Layout } from '../../components/Layout';
import { Card } from '../../components/Card';
import { Table } from '../../components/Table';
import { Button } from '../../components/Button';
import { Badge } from '../../components/Badge';
import { Select } from '../../components/Select';
import { Input } from '../../components/Input';
import { CheckCircle, XCircle, Edit } from 'lucide-react';

export function UsersPage() {
  const [statusFilter, setStatusFilter] = useState('all');
  const [roleFilter, setRoleFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  const usersData = [
    {
      id: 1,
      name: '홍길동',
      username: 'hong',
      email: 'hong@company.com',
      department: '개발팀',
      role: '관리자',
      status: '활성',
      joinDate: '2024-01-15',
      lastLogin: '2024-12-15 14:30'
    },
    {
      id: 2,
      name: '김영희',
      username: 'kim',
      email: 'kim@company.com',
      department: '기획팀',
      role: '일반 사용자',
      status: '활성',
      joinDate: '2024-02-20',
      lastLogin: '2024-12-15 09:15'
    },
    {
      id: 3,
      name: '박철수',
      username: 'park',
      email: 'park@company.com',
      department: '개발팀',
      role: '일반 사용자',
      status: '대기',
      joinDate: '2024-12-14',
      lastLogin: '-'
    },
    {
      id: 4,
      name: '이민수',
      username: 'lee',
      email: 'lee@company.com',
      department: '디자인팀',
      role: '일반 사용자',
      status: '비활성',
      joinDate: '2024-03-10',
      lastLogin: '2024-11-20 16:45'
    }
  ];

  const getStatusBadge = (status: string) => {
    const variants: { [key: string]: 'success' | 'warning' | 'danger' | 'gray' } = {
      '활성': 'success',
      '대기': 'warning',
      '비활성': 'gray',
      '잠금': 'danger'
    };
    return <Badge variant={variants[status] || 'gray'}>{status}</Badge>;
  };

  const getRoleBadge = (role: string) => {
    return <Badge variant={role === '관리자' ? 'primary' : 'info'}>{role}</Badge>;
  };

  const columns = [
    { key: 'name', header: '이름' },
    { key: 'username', header: '아이디' },
    { key: 'email', header: '이메일' },
    { key: 'department', header: '부서' },
    { key: 'role', header: '권한', render: (value: string) => getRoleBadge(value) },
    { key: 'status', header: '상태', render: (value: string) => getStatusBadge(value) },
    { key: 'joinDate', header: '가입일' },
    { key: 'lastLogin', header: '최근 로그인' },
    {
      key: 'actions',
      header: '작업',
      render: (_: any, row: any) => (
        <div className="flex gap-2">
          {row.status === '대기' && (
            <Button variant="outline" size="sm">
              <CheckCircle className="w-4 h-4" />
              승인
            </Button>
          )}
          {row.status === '활성' && (
            <Button variant="outline" size="sm">
              <XCircle className="w-4 h-4" />
              비활성화
            </Button>
          )}
          <Button variant="ghost" size="sm">
            <Edit className="w-4 h-4" />
            수정
          </Button>
        </div>
      )
    }
  ];

  return (
    <Layout>
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl text-gray-900 mb-2">사용자 관리</h1>
          <p className="text-sm text-gray-600">사용자 계정을 관리하고 권한을 설정하세요</p>
        </div>

        <Card className="mb-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Select
              label="계정 상태"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              options={[
                { value: 'all', label: '전체' },
                { value: 'active', label: '활성' },
                { value: 'pending', label: '대기' },
                { value: 'inactive', label: '비활성' },
                { value: 'locked', label: '잠금' }
              ]}
            />
            <Select
              label="권한"
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              options={[
                { value: 'all', label: '전체' },
                { value: 'admin', label: '관리자' },
                { value: 'user', label: '일반 사용자' }
              ]}
            />
            <Input
              label="사용자 검색"
              placeholder="이름, 아이디, 이메일"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg text-gray-900">사용자 목록 ({usersData.length}명)</h2>
          </div>
          <Table columns={columns} data={usersData} />
        </Card>
      </div>
    </Layout>
  );
}
