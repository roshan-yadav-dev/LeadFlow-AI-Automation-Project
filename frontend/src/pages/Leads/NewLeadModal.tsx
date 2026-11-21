import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Modal } from '../../components/common/Modal';
import { leadsService } from '../../services/leads';
import { LeadCreateResponse } from '../../types/leads';
import { CheckCircle2, AlertCircle } from 'lucide-react';

const leadSchema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters').max(100),
  email: z.string().email('Please enter a valid email address'),
  phone: z.string().max(20).optional().or(z.literal('')),
  company: z.string().max(150).optional().or(z.literal('')),
  service: z.string().min(2, 'Service inquiry must be at least 2 characters').max(100),
  requirements: z.string().min(10, 'Requirements must be at least 10 characters').max(3000),
  budget: z.string().max(100).optional().or(z.literal('')),
  preferred_contact: z.literal('email'),
  consent: z.literal(true, {
    errorMap: () => ({ message: 'You must confirm customer consent to process personal data.' }),
  }),
});

type LeadFormData = z.infer<typeof leadSchema>;

interface NewLeadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onLeadCreated: () => void;
}

export const NewLeadModal: React.FC<NewLeadModalProps> = ({
  isOpen,
  onClose,
  onLeadCreated,
}) => {
  const [serverError, setServerError] = useState<string | null>(null);
  const [successResult, setSuccessResult] = useState<LeadCreateResponse | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<LeadFormData>({
    resolver: zodResolver(leadSchema),
    defaultValues: {
      preferred_contact: 'email',
      consent: false as any,
    },
  });

  const handleClose = () => {
    reset();
    setServerError(null);
    setSuccessResult(null);
    onClose();
  };

  const onSubmit = async (data: LeadFormData) => {
    setServerError(null);
    try {
      const result = await leadsService.createLead({
        name: data.name,
        email: data.email,
        phone: data.phone || null,
        company: data.company || null,
        service: data.service,
        requirements: data.requirements,
        budget: data.budget || null,
        preferred_contact: 'email',
        consent: data.consent,
      });

      setSuccessResult(result);
      onLeadCreated();
    } catch (err: any) {
      setServerError(err.message || 'Failed to create lead');
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Capture New Inbound Lead" maxWidth="xl">
      {successResult ? (
        <div className="space-y-4 py-4 text-center">
          <div className="mx-auto w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center">
            <CheckCircle2 className="w-8 h-8" />
          </div>
          <h4 className="text-lg font-bold text-slate-900 dark:text-white">
            Lead Created Successfully!
          </h4>
          <p className="text-sm text-slate-500">
            Assigned Lead ID: <span className="font-mono font-bold text-indigo-600">{successResult.lead_id}</span>
          </p>

          <div className="p-4 bg-slate-50 dark:bg-slate-800 rounded-lg text-left text-xs space-y-1.5 border border-slate-200 dark:border-slate-700">
            <p><span className="font-semibold">AI Personalization:</span> {successResult.ai_status}</p>
            <p><span className="font-semibold">Email Dispatch Status:</span> {successResult.email_status}</p>
            {successResult.email_error && (
              <p className="text-rose-600 font-medium">Notice: {successResult.email_error}</p>
            )}
          </div>

          <div className="pt-4 flex justify-end">
            <button
              onClick={handleClose}
              className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition"
            >
              Done
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {serverError && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-700 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{serverError}</span>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Full Name *
              </label>
              <input
                {...register('name')}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 focus:ring-2 focus:ring-indigo-500"
                placeholder="Jane Doe"
              />
              {errors.name && <p className="text-rose-500 text-xs mt-1">{errors.name.message}</p>}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Email Address *
              </label>
              <input
                {...register('email')}
                type="email"
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 focus:ring-2 focus:ring-indigo-500"
                placeholder="jane@company.com"
              />
              {errors.email && <p className="text-rose-500 text-xs mt-1">{errors.email.message}</p>}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Company Name
              </label>
              <input
                {...register('company')}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 focus:ring-2 focus:ring-indigo-500"
                placeholder="Acme Corp"
              />
              {errors.company && <p className="text-rose-500 text-xs mt-1">{errors.company.message}</p>}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Phone Number
              </label>
              <input
                {...register('phone')}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 focus:ring-2 focus:ring-indigo-500"
                placeholder="+1 555-0199"
              />
              {errors.phone && <p className="text-rose-500 text-xs mt-1">{errors.phone.message}</p>}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Service of Interest *
              </label>
              <input
                {...register('service')}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 focus:ring-2 focus:ring-indigo-500"
                placeholder="Enterprise AI Automation"
              />
              {errors.service && <p className="text-rose-500 text-xs mt-1">{errors.service.message}</p>}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Budget Indication
              </label>
              <input
                {...register('budget')}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 focus:ring-2 focus:ring-indigo-500"
                placeholder="$10,000 - $25,000"
              />
              {errors.budget && <p className="text-rose-500 text-xs mt-1">{errors.budget.message}</p>}
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Requirements / Inbound Note *
            </label>
            <textarea
              {...register('requirements')}
              rows={3}
              className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 focus:ring-2 focus:ring-indigo-500"
              placeholder="Describe customer inquiry, timeline, and use case details..."
            />
            {errors.requirements && (
              <p className="text-rose-500 text-xs mt-1">{errors.requirements.message}</p>
            )}
          </div>

          <div className="pt-2">
            <label className="flex items-start gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                {...register('consent')}
                className="mt-1 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
              <span className="text-xs text-slate-600 dark:text-slate-400">
                Customer has provided explicit consent to receive communications and process their lead data.
              </span>
            </label>
            {errors.consent && (
              <p className="text-rose-500 text-xs mt-1">{errors.consent.message}</p>
            )}
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-slate-700">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition dark:bg-slate-800 dark:text-slate-300 dark:border-slate-600"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition disabled:opacity-50"
            >
              {isSubmitting ? 'Saving & Generating...' : 'Save Lead'}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
};
