import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '../../components/Layout';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { Badge } from '../../components/Badge';
import { FileText, GitCompare } from 'lucide-react';

export function DuplicateDetectionPage() {
  const navigate = useNavigate();

  const identicalFiles = [
    {
      id: 1,
      groupId: 'group1',
      files: [
        { path: '/documents/2024/report.pdf', size: '2.4 MB', modifiedDate: '2024-12-15' },
        { path: '/backup/old/report.pdf', size: '2.4 MB', modifiedDate: '2024-12-10' },
        { path: '/archive/2024-12/report.pdf', size: '2.4 MB', modifiedDate: '2024-12-08' }
      ]
    },
    {
      id: 2,
      groupId: 'group2',
      files: [
        { path: '/code/src/utils/helper.js', size: '15 KB', modifiedDate: '2024-12-14' },
        { path: '/code/backup/helper.js', size: '15 KB', modifiedDate: '2024-11-20' }
      ]
    }
  ];

  const similarDocuments = [
    {
      id: 1,
      file1: {
        path: '/documents/product_spec_v1.pdf',
        size: '2.1 MB',
        modifiedDate: '2024-11-15'
      },
      file2: {
        path: '/documents/product_spec_v2.pdf',
        size: '2.4 MB',
        modifiedDate: '2024-12-15'
      },
      similarity: 92,
      latestVersion: '/documents/product_spec_v2.pdf'
    },
    {
      id: 2,
      file1: {
        path: '/code/api/UserService.java',
        size: '18 KB',
        modifiedDate: '2024-12-10'
      },
      file2: {
        path: '/code/api/UserServiceImpl.java',
        size: '20 KB',
        modifiedDate: '2024-12-12'
      },
      similarity: 85,
      latestVersion: '/code/api/UserServiceImpl.java'
    },
    {
      id: 3,
      file1: {
        path: '/documents/meeting_notes_2024-11.md',
        size: '8 KB',
        modifiedDate: '2024-11-30'
      },
      file2: {
        path: '/documents/meeting_notes_2024-12.md',
        size: '12 KB',
        modifiedDate: '2024-12-01'
      },
      similarity: 78,
      latestVersion: '/documents/meeting_notes_2024-12.md'
    }
  ];

  return (
    <Layout>
      <div className="max-w-6xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl text-gray-900 mb-2">중복/유사 문서 탐지</h1>
          <p className="text-sm text-gray-600">동일하거나 유사한 파일을 탐지하고 정리하세요</p>
        </div>

        <Card className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg text-gray-900">동일 파일 그룹 ({identicalFiles.length}개)</h2>
          </div>
          <p className="text-sm text-gray-600 mb-4">
            다음 파일들은 내용이 완전히 동일합니다. 중복을 제거하여 저장 공간을 절약할 수 있습니다.
          </p>

          <div className="space-y-4">
            {identicalFiles.map((group) => (
              <div key={group.id} className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Badge variant="danger">동일 파일</Badge>
                  <span className="text-sm text-gray-600">{group.files.length}개 파일</span>
                </div>
                <div className="space-y-2">
                  {group.files.map((file, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-3 bg-white rounded border border-gray-200"
                    >
                      <div className="flex items-center gap-3">
                        <FileText className="w-4 h-4 text-gray-400" />
                        <div>
                          <p className="text-sm text-gray-900">{file.path}</p>
                          <div className="flex items-center gap-3 text-xs text-gray-500 mt-1">
                            <span>{file.size}</span>
                            <span>{file.modifiedDate}</span>
                            {index === 0 && (
                              <Badge variant="success" size="sm">최신</Badge>
                            )}
                          </div>
                        </div>
                      </div>
                      <Button variant="ghost" size="sm">
                        상세 보기
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg text-gray-900">유사 문서 후보 ({similarDocuments.length}개)</h2>
          </div>
          <p className="text-sm text-gray-600 mb-4">
            다음 파일들은 내용이 유사합니다. 최신 버전을 확인하고 관리하세요.
          </p>

          <div className="space-y-4">
            {similarDocuments.map((pair) => (
              <div key={pair.id} className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Badge variant="warning">유사도 {pair.similarity}%</Badge>
                  <GitCompare className="w-4 h-4 text-gray-400" />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-3 bg-white rounded border border-gray-200">
                    <div className="flex items-center gap-2 mb-2">
                      <FileText className="w-4 h-4 text-gray-400" />
                      <span className="text-sm text-gray-900">{pair.file1.path.split('/').pop()}</span>
                    </div>
                    <p className="text-xs text-gray-600 mb-2">{pair.file1.path}</p>
                    <div className="flex items-center gap-3 text-xs text-gray-500">
                      <span>{pair.file1.size}</span>
                      <span>{pair.file1.modifiedDate}</span>
                    </div>
                  </div>

                  <div className="p-3 bg-white rounded border border-gray-200">
                    <div className="flex items-center gap-2 mb-2">
                      <FileText className="w-4 h-4 text-gray-400" />
                      <span className="text-sm text-gray-900">{pair.file2.path.split('/').pop()}</span>
                      {pair.file2.path === pair.latestVersion && (
                        <Badge variant="success" size="sm">최신 버전</Badge>
                      )}
                    </div>
                    <p className="text-xs text-gray-600 mb-2">{pair.file2.path}</p>
                    <div className="flex items-center gap-3 text-xs text-gray-500">
                      <span>{pair.file2.size}</span>
                      <span>{pair.file2.modifiedDate}</span>
                    </div>
                  </div>
                </div>

                <div className="mt-3 flex gap-2">
                  <Button variant="outline" size="sm">
                    <GitCompare className="w-4 h-4" />
                    비교하기
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </Layout>
  );
}
