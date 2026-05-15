import React, { useState } from 'react';
import { Layout } from '../../components/Layout';
import { Card } from '../../components/Card';
import { Input } from '../../components/Input';
import { Select } from '../../components/Select';
import { Button } from '../../components/Button';
import { Badge } from '../../components/Badge';
import { Table } from '../../components/Table';
import { Modal } from '../../components/Modal';
import { CheckCircle, XCircle, TestTube, Edit, Play, Pause, Plus, AlertTriangle } from 'lucide-react';

interface DataSource {
  id: number;
  name: string;
  type: 'ownCloud' | 'Nextcloud' | 'Generic WebDAV';
  serverUrl: string;
  webdavPath: string;
  status: '활성' | '비활성' | '오류';
  lastAnalyzed: string;
}

export function DataSourceSettingsPage() {
  const [dataSources, setDataSources] = useState<DataSource[]>([
    {
      id: 1,
      name: '사내 문서함',
      type: 'ownCloud',
      serverUrl: 'https://cloud.company.com',
      webdavPath: '/remote.php/dav/files/admin',
      status: '활성',
      lastAnalyzed: '2024-12-15 14:30'
    },
    {
      id: 2,
      name: '고객사 A WebDAV',
      type: 'Nextcloud',
      serverUrl: 'https://nextcloud.client-a.com',
      webdavPath: '/remote.php/dav/files/shared',
      status: '활성',
      lastAnalyzed: '2024-12-14 22:15'
    },
    {
      id: 3,
      name: '테스트 WebDAV',
      type: 'Generic WebDAV',
      serverUrl: 'https://webdav.test.local',
      webdavPath: '/dav',
      status: '비활성',
      lastAnalyzed: '2024-12-10 10:00'
    }
  ]);

  const [showModal, setShowModal] = useState(false);
  const [editingSource, setEditingSource] = useState<DataSource | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    type: 'ownCloud',
    serverUrl: '',
    webdavPath: '',
    userId: '',
    password: '',
    description: '',
    isActive: true
  });

  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const handleAddNew = () => {
    setEditingSource(null);
    setFormData({
      name: '',
      type: 'ownCloud',
      serverUrl: '',
      webdavPath: '',
      userId: '',
      password: '',
      description: '',
      isActive: true
    });
    setTestResult(null);
    setShowModal(true);
  };

  const handleEdit = (source: DataSource) => {
    setEditingSource(source);
    setFormData({
      name: source.name,
      type: source.type,
      serverUrl: source.serverUrl,
      webdavPath: source.webdavPath,
      userId: 'admin',
      password: '****-****-****-****',
      description: '',
      isActive: source.status === '활성'
    });
    setTestResult(null);
    setShowModal(true);
  };

  const handleTest = () => {
    setTestResult({
      success: true,
      message: '접속 성공! WebDAV 연결이 정상적으로 작동합니다.'
    });
  };

  const handleSave = () => {
    alert('데이터 소스가 저장되었습니다.');
    setShowModal(false);
  };

  const handleCloneAndSave = () => {
    alert('새 데이터 소스로 복제 저장되었습니다.');
    setShowModal(false);
  };

  const getStatusBadge = (status: string) => {
    const variants: { [key: string]: 'success' | 'gray' | 'danger' } = {
      '활성': 'success',
      '비활성': 'gray',
      '오류': 'danger'
    };
    return <Badge variant={variants[status]}>{status}</Badge>;
  };

  const getTypeBadge = (type: string) => {
    const variants: { [key: string]: 'primary' | 'info' | 'gray' } = {
      'ownCloud': 'primary',
      'Nextcloud': 'info',
      'Generic WebDAV': 'gray'
    };
    return <Badge variant={variants[type]}>{type}</Badge>;
  };

  const columns = [
    { key: 'name', header: '데이터 소스명', width: '200px' },
    {
      key: 'type',
      header: '유형',
      render: (value: string) => getTypeBadge(value)
    },
    { key: 'serverUrl', header: '서버 URL', width: '250px' },
    { key: 'webdavPath', header: 'WebDAV 루트 경로', width: '250px' },
    {
      key: 'status',
      header: '상태',
      render: (value: string) => getStatusBadge(value)
    },
    { key: 'lastAnalyzed', header: '마지막 분석', width: '150px' },
    {
      key: 'actions',
      header: '작업',
      width: '280px',
      render: (_: any, row: DataSource) => (
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => handleEdit(row)}>
            <Edit className="w-4 h-4" />
            수정
          </Button>
          <Button variant="ghost" size="sm">
            <TestTube className="w-4 h-4" />
            테스트
          </Button>
          <Button variant="ghost" size="sm">
            <Play className="w-4 h-4" />
            분석
          </Button>
          {row.status === '활성' ? (
            <Button variant="ghost" size="sm">
              <Pause className="w-4 h-4" />
            </Button>
          ) : (
            <Button variant="ghost" size="sm">
              <Play className="w-4 h-4" />
            </Button>
          )}
        </div>
      )
    }
  ];

  return (
    <Layout>
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl text-gray-900 mb-2">데이터 소스 설정</h1>
          <p className="text-sm text-gray-600">WebDAV 기반 저장소를 데이터 소스로 등록하고 관리하세요</p>
        </div>

        <Card className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg text-gray-900">등록된 데이터 소스 ({dataSources.length}개)</h2>
            <Button variant="primary" onClick={handleAddNew}>
              <Plus className="w-4 h-4" />
              데이터 소스 추가
            </Button>
          </div>
          <Table columns={columns} data={dataSources} />
        </Card>

        <Modal
          isOpen={showModal}
          onClose={() => setShowModal(false)}
          title={editingSource ? '데이터 소스 수정' : '새 데이터 소스 등록'}
          size="lg"
          footer={
            <div className="flex gap-3">
              <Button variant="primary" onClick={handleSave}>
                저장
              </Button>
              {editingSource && (
                <Button variant="outline" onClick={handleCloneAndSave}>
                  새 데이터 소스로 복제 저장
                </Button>
              )}
              <Button variant="secondary" onClick={() => setShowModal(false)}>
                취소
              </Button>
            </div>
          }
        >
          <div className="space-y-4">
            {editingSource && (
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 flex gap-3">
                <AlertTriangle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-yellow-800">
                  서버 URL 또는 WebDAV 루트 경로를 변경하면 기존 분석 데이터와 다른 저장소로 인식될 수 있습니다.
                  다른 저장소라면 새 데이터 소스로 등록하는 것을 권장합니다.
                </p>
              </div>
            )}

            <Input
              label="데이터 소스명"
              type="text"
              placeholder="예: 사내 문서함"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              helperText="사용자가 식별하기 쉬운 이름을 입력하세요"
            />

            <Select
              label="데이터 소스 유형"
              value={formData.type}
              onChange={(e) => setFormData({ ...formData, type: e.target.value })}
              options={[
                { value: 'ownCloud', label: 'ownCloud' },
                { value: 'Nextcloud', label: 'Nextcloud' },
                { value: 'Generic WebDAV', label: 'Generic WebDAV' },
                { value: 'Local Folder', label: 'Local Folder (추후 지원)' }
              ]}
            />

            <Input
              label="서버 URL"
              type="url"
              placeholder="https://cloud.example.com"
              value={formData.serverUrl}
              onChange={(e) => setFormData({ ...formData, serverUrl: e.target.value })}
              helperText="WebDAV 서버의 전체 URL을 입력하세요"
            />

            <Input
              label="WebDAV 루트 경로"
              type="text"
              placeholder="/remote.php/dav/files/username"
              value={formData.webdavPath}
              onChange={(e) => setFormData({ ...formData, webdavPath: e.target.value })}
              helperText="WebDAV 프로토콜에 접근할 수 있는 루트 경로"
            />

            <Input
              label="사용자 ID"
              type="text"
              placeholder="admin"
              value={formData.userId}
              onChange={(e) => setFormData({ ...formData, userId: e.target.value })}
              helperText="WebDAV 인증에 사용할 사용자 계정"
            />

            <Input
              label="비밀번호 또는 App Password"
              type="password"
              placeholder="비밀번호 또는 앱 전용 비밀번호를 입력하세요"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              helperText="보안을 위해 앱 전용 비밀번호 사용을 권장합니다"
            />

            <Input
              label="설명 (선택)"
              type="text"
              placeholder="이 데이터 소스에 대한 간단한 설명"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            />

            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div>
                <p className="text-sm text-gray-900">활성 여부</p>
                <p className="text-xs text-gray-600">비활성화하면 분석 및 검색에서 제외됩니다</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.isActive}
                  onChange={(e) => setFormData({ ...formData, isActive: e.target.checked })}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>

            <div className="flex gap-3 pt-4">
              <Button variant="secondary" onClick={handleTest} className="flex-1">
                <TestTube className="w-4 h-4" />
                접속 테스트
              </Button>
            </div>

            {testResult && (
              <div
                className={`flex items-start gap-4 p-4 rounded-lg border ${
                  testResult.success
                    ? 'bg-green-50 border-green-200'
                    : 'bg-red-50 border-red-200'
                }`}
              >
                {testResult.success ? (
                  <CheckCircle className="w-6 h-6 text-green-600 flex-shrink-0" />
                ) : (
                  <XCircle className="w-6 h-6 text-red-600 flex-shrink-0" />
                )}
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <Badge variant={testResult.success ? 'success' : 'danger'}>
                      {testResult.success ? '성공' : '실패'}
                    </Badge>
                  </div>
                  <p className={`text-sm ${testResult.success ? 'text-green-800' : 'text-red-800'}`}>
                    {testResult.message}
                  </p>
                </div>
              </div>
            )}
          </div>
        </Modal>
      </div>
    </Layout>
  );
}
