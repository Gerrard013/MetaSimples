document.addEventListener('DOMContentLoaded', () => {
    const flashes = document.querySelectorAll('.flash');

    if (flashes.length) {
        setTimeout(() => {
            flashes.forEach((item) => {
                item.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
                item.style.opacity = '0';
                item.style.transform = 'translateY(-4px)';

                setTimeout(() => {
                    item.remove();
                }, 360);
            });
        }, 3500);
    }

    const useCommissionInput = document.getElementById('use_commission');
    const commissionField = document.getElementById('commissionField');
    const commissionInput = commissionField ? commissionField.querySelector('input') : null;

    const syncCommissionState = () => {
        if (!useCommissionInput || !commissionField || !commissionInput) return;

        const enabled = useCommissionInput.checked;
        commissionField.classList.toggle('is-disabled', !enabled);
        commissionInput.disabled = !enabled;

        if (!enabled) {
            commissionInput.value = '';
        }
    };

    if (useCommissionInput) {
        syncCommissionState();
        useCommissionInput.addEventListener('change', syncCommissionState);
    }

    const emailRegex = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

    const normalizeWhatsapp = (value) => {
        return value.replace(/\D/g, '').replace(/^55(?=\d{11}$)/, '');
    };

    const formatWhatsapp = (value) => {
        const digits = normalizeWhatsapp(value).slice(0, 11);

        if (digits.length <= 2) return digits;
        if (digits.length <= 7) return `(${digits.slice(0, 2)}) ${digits.slice(2)}`;

        return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7, 11)}`;
    };

    const isValidWhatsapp = (value) => {
        const digits = normalizeWhatsapp(value);

        if (digits.length !== 11) return false;

        const ddd = Number(digits.slice(0, 2));
        const repeatedDigitsRegex = /^(\d)\1{10}$/;

        return ddd >= 11 && ddd <= 99 && digits[2] === '9' && !repeatedDigitsRegex.test(digits);
    };

    document.querySelectorAll('[data-whatsapp-check="true"]').forEach((input) => {
        input.addEventListener('input', () => {
            input.value = formatWhatsapp(input.value);
        });
    });

    const setFeedback = (fieldName, message, type = 'error') => {
        const node = document.querySelector(`[data-feedback-for="${fieldName}"]`);
        if (!node) return;

        node.textContent = message || '';
        node.classList.remove('feedback-success', 'feedback-error');

        if (message) {
            node.classList.add(type === 'success' ? 'feedback-success' : 'feedback-error');
        }
    };

    const checkEmailField = async (input) => {
        const value = input.value.trim().toLowerCase();

        if (!value) {
            setFeedback('email', '');
            return true;
        }

        if (!emailRegex.test(value)) {
            setFeedback('email', 'Informe um e-mail válido.');
            return false;
        }

        try {
            const response = await fetch(`/api/validate/email?email=${encodeURIComponent(value)}`);
            const data = await response.json();

            if (!data.valid) {
                setFeedback('email', 'Informe um e-mail válido.');
                return false;
            }

            if (data.exists) {
                setFeedback('email', 'Este e-mail já está cadastrado.');
                return false;
            }

            setFeedback('email', 'E-mail disponível.', 'success');
            return true;
        } catch (error) {
            setFeedback('email', 'Não foi possível validar o e-mail agora.');
            return false;
        }
    };

    const checkWhatsappField = async (input) => {
        const value = input.value.trim();

        if (!value) {
            setFeedback('whatsapp', '');
            return true;
        }

        if (!isValidWhatsapp(value)) {
            setFeedback('whatsapp', 'WhatsApp inválido. Use DDD + 9 dígitos.');
            return false;
        }

        try {
            const response = await fetch(`/api/validate/whatsapp?whatsapp=${encodeURIComponent(value)}`);
            const data = await response.json();

            if (!data.valid) {
                setFeedback('whatsapp', 'WhatsApp inválido. Use DDD + 9 dígitos.');
                return false;
            }

            if (data.exists) {
                setFeedback('whatsapp', 'Este WhatsApp já está cadastrado.');
                return false;
            }

            setFeedback('whatsapp', 'WhatsApp válido.', 'success');
            return true;
        } catch (error) {
            setFeedback('whatsapp', 'Não foi possível validar o WhatsApp agora.');
            return false;
        }
    };

    const emailInput = document.querySelector('[data-email-check="true"]');
    const whatsappInput = document.querySelector('[data-whatsapp-check="true"]');

    if (emailInput) {
        emailInput.addEventListener('blur', () => checkEmailField(emailInput));
    }

    if (whatsappInput) {
        whatsappInput.addEventListener('blur', () => checkWhatsappField(whatsappInput));
    }

    document.querySelectorAll('[data-validate-form]').forEach((form) => {
        form.addEventListener('submit', async (event) => {
            let valid = true;

            const localEmailInput = form.querySelector('[data-email-check="true"]');
            const localWhatsappInput = form.querySelector('[data-whatsapp-check="true"]');

            if (localEmailInput) {
                valid = (await checkEmailField(localEmailInput)) && valid;
            }

            if (localWhatsappInput) {
                valid = (await checkWhatsappField(localWhatsappInput)) && valid;
            }

            if (!valid) {
                event.preventDefault();
            }
        });
    });
});