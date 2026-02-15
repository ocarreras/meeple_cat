'use client';

import { useTranslation } from 'react-i18next';
import { useRouter } from 'next/navigation';

const LOCALES = [
  { code: 'en', label: 'EN' },
  { code: 'ca', label: 'CA' },
];

export default function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const router = useRouter();

  const handleChange = (locale: string) => {
    document.cookie = `NEXT_LOCALE=${locale};path=/;max-age=${60 * 60 * 24 * 365};samesite=lax`;
    i18n.changeLanguage(locale);
    router.refresh();
  };

  return (
    <div className="flex items-center gap-1 text-sm">
      {LOCALES.map(({ code, label }) => (
        <button
          key={code}
          onClick={() => handleChange(code)}
          className={`px-2 py-1 rounded transition ${
            i18n.language === code
              ? 'bg-gray-200 text-gray-800 font-semibold'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
