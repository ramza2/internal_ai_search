import React from 'react';
import { Layout } from '../../components/Layout';
import { Card } from '../../components/Card';
import { BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export function FileAnalyticsPage() {
  const extensionData = [
    { name: 'pdf', count: 3200, size: '15.2 GB' },
    { name: 'docx', count: 2800, size: '8.4 GB' },
    { name: 'java', count: 2100, size: '2.1 GB' },
    { name: 'py', count: 1800, size: '1.5 GB' },
    { name: 'xlsx', count: 1500, size: '5.8 GB' },
    { name: 'md', count: 980, size: '0.2 GB' }
  ];

  const typeData = [
    { name: '문서', count: 7500, size: '29.4 GB', color: '#3b82f6' },
    { name: '소스 코드', count: 3900, size: '3.6 GB', color: '#10b981' },
    { name: '이미지', count: 890, size: '12.8 GB', color: '#f59e0b' },
    { name: '압축 파일', count: 290, size: '18.5 GB', color: '#ef4444' }
  ];

  const stats = {
    analyzableFiles: 11245,
    nonAnalyzableFiles: 1335,
    totalSize: '64.3 GB'
  };

  return (
    <Layout>
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl text-gray-900 mb-2">파일 현황 분석</h1>
          <p className="text-sm text-gray-600">ownCloud 내 파일 유형별 분포를 확인하세요</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
          <Card>
            <h3 className="text-sm text-gray-600 mb-2">분석 가능 파일</h3>
            <p className="text-2xl text-green-600">{stats.analyzableFiles.toLocaleString()}</p>
          </Card>
          <Card>
            <h3 className="text-sm text-gray-600 mb-2">분석 불가 파일</h3>
            <p className="text-2xl text-red-600">{stats.nonAnalyzableFiles.toLocaleString()}</p>
          </Card>
          <Card>
            <h3 className="text-sm text-gray-600 mb-2">전체 용량</h3>
            <p className="text-2xl text-blue-600">{stats.totalSize}</p>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          <Card>
            <h2 className="text-lg text-gray-900 mb-4">확장자별 파일 수</h2>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={extensionData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="count" fill="#3b82f6" name="파일 수" />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card>
            <h2 className="text-lg text-gray-900 mb-4">문서 유형별 분포</h2>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={typeData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="count"
                >
                  {typeData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </Card>
        </div>

        <Card>
          <h2 className="text-lg text-gray-900 mb-4">상세 통계</h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="px-4 py-3 text-left text-sm text-gray-700">확장자</th>
                  <th className="px-4 py-3 text-left text-sm text-gray-700">파일 수</th>
                  <th className="px-4 py-3 text-left text-sm text-gray-700">총 용량</th>
                </tr>
              </thead>
              <tbody>
                {extensionData.map((item) => (
                  <tr key={item.name} className="border-b border-gray-100">
                    <td className="px-4 py-3 text-sm text-gray-900">{item.name}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{item.count.toLocaleString()}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{item.size}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </Layout>
  );
}
