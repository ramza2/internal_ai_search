import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  Search,
  MessageSquare,
  LayoutDashboard,
  Settings,
  BarChart3,
  RefreshCw,
  FolderX,
  Users,
  FileText,
  AlertCircle,
  Brain,
  Copy,
  X
} from 'lucide-react';

interface MenuItem {
  path: string;
  label: string;
  icon: React.ReactNode;
}

interface SidebarProps {
  isAdmin?: boolean;
  isOpen?: boolean;
  onClose?: () => void;
}

export function Sidebar({ isAdmin = true, isOpen = false, onClose }: SidebarProps) {
  const location = useLocation();

  const userMenuItems: MenuItem[] = [
    { path: '/', label: '통합 검색', icon: <Search className="w-5 h-5" /> },
    { path: '/ai-search', label: 'AI 질문', icon: <MessageSquare className="w-5 h-5" /> }
  ];

  const adminMenuItems: MenuItem[] = [
    { path: '/admin/dashboard', label: '관리자 대시보드', icon: <LayoutDashboard className="w-5 h-5" /> },
    { path: '/admin/datasource-settings', label: '데이터 소스 설정', icon: <Settings className="w-5 h-5" /> },
    { path: '/admin/file-analytics', label: '파일 현황 분석', icon: <BarChart3 className="w-5 h-5" /> },
    { path: '/admin/indexing', label: '인덱싱 관리', icon: <RefreshCw className="w-5 h-5" /> },
    { path: '/admin/exclusion-policy', label: '제외 정책 관리', icon: <FolderX className="w-5 h-5" /> },
    { path: '/admin/users', label: '사용자 관리', icon: <Users className="w-5 h-5" /> },
    { path: '/admin/logs', label: '작업 로그', icon: <FileText className="w-5 h-5" /> },
    { path: '/admin/failed-files', label: '분석 실패 파일', icon: <AlertCircle className="w-5 h-5" /> },
    { path: '/admin/rag-settings', label: 'RAG/LLM 설정', icon: <Brain className="w-5 h-5" /> },
    { path: '/admin/duplicate-detection', label: '중복 문서 탐지', icon: <Copy className="w-5 h-5" /> }
  ];

  const isActive = (path: string) => {
    if (path === '/') {
      return location.pathname === '/';
    }
    return location.pathname.startsWith(path);
  };

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}
      <aside className={`
        fixed lg:static inset-y-0 left-0 z-50
        w-64 bg-white border-r border-gray-200 h-screen overflow-y-auto
        transform transition-transform duration-300 ease-in-out
        ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        <div className="flex items-center justify-between p-4 lg:hidden border-b border-gray-200">
          <h2 className="text-sm text-gray-900">메뉴</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-600" />
          </button>
        </div>
        <nav className="p-4">
          <div className="mb-6">
            <h2 className="text-xs uppercase text-gray-500 mb-2 px-3">사용자 메뉴</h2>
            <ul className="space-y-1">
              {userMenuItems.map((item) => (
                <li key={item.path}>
                  <Link
                    to={item.path}
                    onClick={onClose}
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                      isActive(item.path)
                        ? 'bg-blue-50 text-blue-600'
                        : 'text-gray-700 hover:bg-gray-100'
                    }`}
                  >
                    {item.icon}
                    <span className="text-sm">{item.label}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {isAdmin && (
            <div>
              <h2 className="text-xs uppercase text-gray-500 mb-2 px-3">관리자 메뉴</h2>
              <ul className="space-y-1">
                {adminMenuItems.map((item) => (
                  <li key={item.path}>
                    <Link
                      to={item.path}
                      onClick={onClose}
                      className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                        isActive(item.path)
                          ? 'bg-blue-50 text-blue-600'
                          : 'text-gray-700 hover:bg-gray-100'
                      }`}
                    >
                      {item.icon}
                      <span className="text-sm">{item.label}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </nav>
      </aside>
    </>
  );
}
