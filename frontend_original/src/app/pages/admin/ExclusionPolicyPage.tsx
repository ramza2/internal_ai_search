import React, { useState } from 'react';
import { Layout } from '../../components/Layout';
import { Card } from '../../components/Card';
import { Input } from '../../components/Input';
import { Button } from '../../components/Button';
import { Badge } from '../../components/Badge';
import { X, Plus, AlertCircle } from 'lucide-react';

export function ExclusionPolicyPage() {
  const [excludedFolders, setExcludedFolders] = useState([
    '.git', '.svn', 'node_modules', 'build', 'dist', 'target', 'out',
    '.gradle', '.idea', '.vscode', 'venv', '.venv', '__pycache__',
    'tmp', 'temp', 'backup'
  ]);

  const [excludedExtensions, setExcludedExtensions] = useState([
    'exe', 'dll', 'so', 'class', 'jar', 'war', 'zip', '7z', 'rar',
    'tar', 'gz', 'mp4', 'avi', 'mov', 'mp3', 'wav', 'png', 'jpg',
    'jpeg', 'gif', 'psd'
  ]);

  const [maxFileSize, setMaxFileSize] = useState('100');
  const [analyzeArchives, setAnalyzeArchives] = useState(false);
  const [analyzeImagesOCR, setAnalyzeImagesOCR] = useState(false);

  const [newFolder, setNewFolder] = useState('');
  const [newExtension, setNewExtension] = useState('');

  const addFolder = () => {
    if (newFolder && !excludedFolders.includes(newFolder)) {
      setExcludedFolders([...excludedFolders, newFolder]);
      setNewFolder('');
    }
  };

  const removeFolder = (folder: string) => {
    setExcludedFolders(excludedFolders.filter(f => f !== folder));
  };

  const addExtension = () => {
    if (newExtension && !excludedExtensions.includes(newExtension)) {
      setExcludedExtensions([...excludedExtensions, newExtension]);
      setNewExtension('');
    }
  };

  const removeExtension = (ext: string) => {
    setExcludedExtensions(excludedExtensions.filter(e => e !== ext));
  };

  const handleSave = () => {
    alert('제외 정책이 저장되었습니다.');
  };

  return (
    <Layout>
      <div className="max-w-5xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl text-gray-900 mb-2">제외 정책 관리</h1>
          <p className="text-sm text-gray-600">분석에서 제외할 폴더 및 확장자를 설정하세요</p>
        </div>

        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6 flex gap-3">
          <AlertCircle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-yellow-800">
            <p className="mb-1">제외 정책 변경 시 다음 인덱싱부터 적용됩니다.</p>
            <p>이미 분석된 파일은 즉시 제외되지 않습니다.</p>
          </div>
        </div>

        <Card className="mb-6">
          <h2 className="text-lg text-gray-900 mb-4">제외 폴더 목록</h2>
          <p className="text-sm text-gray-600 mb-4">
            다음 폴더는 분석에서 제외됩니다. (와일드카드 지원)
          </p>

          <div className="flex gap-2 mb-4">
            <Input
              placeholder="폴더명 입력 (예: node_modules)"
              value={newFolder}
              onChange={(e) => setNewFolder(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && addFolder()}
            />
            <Button variant="outline" onClick={addFolder}>
              <Plus className="w-4 h-4" />
              추가
            </Button>
          </div>

          <div className="flex flex-wrap gap-2">
            {excludedFolders.map((folder) => (
              <Badge key={folder} variant="gray">
                <span className="font-mono text-xs">{folder}</span>
                <button
                  onClick={() => removeFolder(folder)}
                  className="ml-2 hover:text-red-600 transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </Badge>
            ))}
          </div>
        </Card>

        <Card className="mb-6">
          <h2 className="text-lg text-gray-900 mb-4">제외 확장자 목록</h2>
          <p className="text-sm text-gray-600 mb-4">
            다음 확장자를 가진 파일은 분석에서 제외됩니다.
          </p>

          <div className="flex gap-2 mb-4">
            <Input
              placeholder="확장자 입력 (예: exe)"
              value={newExtension}
              onChange={(e) => setNewExtension(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && addExtension()}
            />
            <Button variant="outline" onClick={addExtension}>
              <Plus className="w-4 h-4" />
              추가
            </Button>
          </div>

          <div className="flex flex-wrap gap-2">
            {excludedExtensions.map((ext) => (
              <Badge key={ext} variant="gray">
                <span className="font-mono text-xs">{ext}</span>
                <button
                  onClick={() => removeExtension(ext)}
                  className="ml-2 hover:text-red-600 transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </Badge>
            ))}
          </div>
        </Card>

        <Card className="mb-6">
          <h2 className="text-lg text-gray-900 mb-4">기타 설정</h2>
          <div className="space-y-4">
            <div>
              <Input
                label="최대 파일 크기 (MB)"
                type="number"
                value={maxFileSize}
                onChange={(e) => setMaxFileSize(e.target.value)}
                helperText="이 크기를 초과하는 파일은 분석하지 않습니다"
              />
            </div>

            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div>
                <p className="text-sm text-gray-900">압축 파일 분석</p>
                <p className="text-xs text-gray-600">ZIP, RAR 등 압축 파일 내부를 분석합니다</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={analyzeArchives}
                  onChange={(e) => setAnalyzeArchives(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>

            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div>
                <p className="text-sm text-gray-900">이미지 OCR 분석</p>
                <p className="text-xs text-gray-600">이미지 파일에서 텍스트를 추출합니다 (처리 시간 증가)</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={analyzeImagesOCR}
                  onChange={(e) => setAnalyzeImagesOCR(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>
          </div>
        </Card>

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
